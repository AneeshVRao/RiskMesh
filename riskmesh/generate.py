"""Synthetic transaction generator: entities, correlated normal behaviour, and
the two Tier 0 injectors (shared-device ring, family hard negative).

Two rules govern this module.

1. **All randomness comes from one `random.Random(cfg.seed)`, passed explicitly.**
   The global `random` module is never touched -- that is the usual way a
   "reproducible" generator quietly stops being reproducible.

2. **Ground truth never touches the transaction stream.** `generate()` returns
   `(transactions, labels)` as two separate lists. A `Txn` has no field naming a
   ring, a cluster, or a class. Everything downstream of here computes features
   from `Txn` alone; only `split.py`, `integrity.py` and `evaluate.py` are
   allowed to open the labels.

Time is measured in **minutes since the start of the observation window**.
`signup_day` may be negative: an account that predates the window has real
tenure without having transacted inside it, which is what lets a family cluster
be simultaneously long-lived and confined to a single chronological period.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import NamedTuple

from .config import Config

MINUTES_PER_DAY = 24 * 60

# Merchant categories with a (mu, sigma) lognormal amount profile in rupees.
CATEGORIES: dict[str, tuple[float, float]] = {
    "ecommerce": (6.4, 0.8),
    "food": (5.6, 0.6),
    "travel": (8.2, 0.9),
    "gaming": (5.9, 1.0),
    "utilities": (6.8, 0.5),
    "subscription": (5.2, 0.4),
}

# Diurnal weighting, midnight..23:00. Payments cluster around lunch and evening.
HOUR_WEIGHTS: tuple[float, ...] = (
    0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.5, 1.0, 1.8, 2.4, 2.8, 3.0,
    3.4, 3.0, 2.6, 2.4, 2.6, 3.0, 3.6, 4.0, 3.6, 2.6, 1.4, 0.6,
)


class Txn(NamedTuple):
    """One transaction. Deliberately carries no label of any kind."""

    txn_id: str
    ts_minute: int
    account_id: str
    device_id: str
    ip_id: str
    instrument_id: str
    merchant_id: str
    amount: float
    status: str  # "captured" | "failed"
    is_refund: int
    # Account age at transaction time. Platform metadata a real processor has at
    # authorisation, not a label -- the scorer is allowed to see it.
    account_age_days: int


class Label(NamedTuple):
    """Ground truth, stored separately from the transaction stream."""

    account_id: str
    ring_id: str  # "" when the account is not a ring member
    cluster_id: str  # "" when the account is not in a family cluster
    active_period: str  # "" for background accounts, which span the window
    ring_type: str = ""  # "" | device | ip | instrument | refund | hybrid


@dataclass
class Merchant:
    merchant_id: str
    category: str
    popularity: float


@dataclass
class Account:
    account_id: str
    home_device: str
    secondary_device: str
    home_ip: str
    instruments: list[str]
    signup_day: int  # negative == predates the observation window
    merchants: list[str]
    amount_mult: float
    refund_rate: float
    failure_rate: float
    kind: str = "background"  # background | ring | family
    active_period: str = ""
    shared_device: str = ""  # ring/family shared device, when applicable
    shared_ip: str = ""  # shared-IP / hybrid ring's converged IP
    ring_id: str = ""
    ring_type: str = ""  # "" | device | ip | instrument | refund | hybrid
    cluster_id: str = ""
    extra: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# entities
# --------------------------------------------------------------------------


def _build_merchants(cfg: Config, rng: random.Random) -> list[Merchant]:
    """Merchants on a popularity power law -- a few giants, a long tail.

    The power law matters: it is what makes merchant edges useless for linking
    accounts (everyone touches the giants) and it is why graph.py excludes them
    from component formation.
    """
    cats = list(CATEGORIES)
    return [
        Merchant(f"m{i:03d}", rng.choice(cats), 1.0 / (i + 1) ** 1.1)
        for i in range(cfg.n_merchants)
    ]


def _build_nat_ips(cfg: Config) -> list[str]:
    """Carrier-grade NAT IPs: shared by hundreds of unrelated accounts.

    This is the 'common infrastructure' the PRD warns about. It exists so the
    graph hygiene rules in graph.py have something real to defend against.
    """
    return [f"ip_nat{i:02d}" for i in range(cfg.n_nat_ips)]


def _new_account(
    cfg: Config,
    rng: random.Random,
    idx: int,
    merchants: list[Merchant],
    pop_weights: list[float],
    signup_day: int,
    kind: str = "background",
) -> Account:
    """One account with a coherent behavioural profile.

    The profile is what makes the data correlated rather than independent rows:
    a sticky merchant set, a personal amount multiplier, its own device and IP.
    """
    n_pref = rng.randint(3, 6)
    picks = rng.choices(merchants, weights=pop_weights, k=n_pref * 2)
    preferred: list[str] = []
    for m in picks:
        if m.merchant_id not in preferred:
            preferred.append(m.merchant_id)
        if len(preferred) == n_pref:
            break

    aid = f"a{idx:05d}"
    return Account(
        account_id=aid,
        home_device=f"d_{aid}",
        secondary_device=f"d2_{aid}",
        home_ip=f"ip_home_{aid}",
        instruments=[f"pi_{aid}"],
        signup_day=signup_day,
        merchants=preferred,
        amount_mult=rng.lognormvariate(0.0, 0.35),
        refund_rate=cfg.base_refund_rate,
        failure_rate=cfg.base_failure_rate,
        kind=kind,
    )


def _build_background(
    cfg: Config, rng: random.Random, merchants: list[Merchant], pop_weights: list[float]
) -> list[Account]:
    """The ordinary population, plus unlabelled sharing noise.

    The noise is load-bearing. Without a background of accounts that innocently
    share a device or a card, "two accounts share a device" separates the classes
    perfectly and every metric in the benchmark becomes meaningless.
    """
    accounts = [
        _new_account(
            cfg, rng, i, merchants, pop_weights,
            signup_day=rng.randint(-540, cfg.days - 5),
        )
        for i in range(cfg.n_accounts)
    ]

    for _ in range(cfg.n_noise_shared_devices):
        a, b = rng.sample(accounts, 2)
        b.home_device = a.home_device
    for _ in range(cfg.n_noise_shared_instruments):
        a, b = rng.sample(accounts, 2)
        if a.instruments[0] not in b.instruments:
            b.instruments.append(a.instruments[0])

    return accounts


# --------------------------------------------------------------------------
# transaction emission
# --------------------------------------------------------------------------


def _pick_ip(cfg: Config, rng: random.Random, acct: Account, nat_ips: list[str]) -> str:
    """Mirrors `_pick_device`: a shared-IP/hybrid ring member routes most (not
    all) traffic through the ring's converged IP -- this is what finally gives
    `ip_sharing` a ring type to measure (config.py's `ip_sharing` comment).

    Unlike `_pick_device` (unchanged, Tier 0), nothing here is short-circuited
    on `acct.shared_ip`. The non-shared fallback is computed UNCONDITIONALLY,
    even on the branch that ends up returning `shared_ip` instead -- an early
    return that skipped it would make word count depend on whether the
    fallback happened to need `rng.choice(nat_ips)`/`rng.randrange(400)`,
    which is exactly the class of bug an `if acct.shared_ip and ...: return`
    short-circuit reintroduces one line later than it looks. `_pick_device`'s
    own short-circuit is a pre-existing Tier 0 property this task leaves
    alone; this function is new, so it does not need to repeat it.
    """
    use_shared = rng.random() < acct.extra.get("shared_ip_share", 1.0)
    r = rng.random()
    if r < cfg.p_home_ip:
        fallback = acct.home_ip
    elif r < cfg.p_home_ip + cfg.p_nat_ip:
        fallback = rng.choice(nat_ips)
    else:
        fallback = f"ip_travel{rng.randrange(400):03d}"
    return acct.shared_ip if (acct.shared_ip and use_shared) else fallback


def _pick_device(cfg: Config, rng: random.Random, acct: Account) -> str:
    """Ring members route most traffic through the shared device -- but not all.

    `ring_shared_device_share` is deliberately below 1.0. A ring whose members
    *only* ever use the shared device is trivially separable, and a benchmark
    built on that proves nothing.
    """
    if acct.shared_device and rng.random() < acct.extra.get("shared_device_share", 1.0):
        return acct.shared_device
    return acct.home_device if rng.random() < cfg.p_home_device else acct.secondary_device


def _pick_merchant(cfg: Config, rng: random.Random, acct: Account,
                   merchants: list[Merchant], pop_weights: list[float]) -> str:
    if rng.random() < cfg.p_sticky_merchant:
        return rng.choice(acct.merchants)
    return rng.choices(merchants, weights=pop_weights, k=1)[0].merchant_id


def _timestamp(rng: random.Random, day: int) -> int:
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
    return day * MINUTES_PER_DAY + hour * 60 + rng.randrange(60)


def _emit(
    cfg: Config,
    rng: random.Random,
    acct: Account,
    day_lo: int,
    day_hi: int,
    n: int,
    merchants: list[Merchant],
    pop_weights: list[float],
    by_id: dict[str, Merchant],
    nat_ips: list[str],
    out: list[Txn],
) -> None:
    """Emit `n` ordinary transactions for one account inside [day_lo, day_hi)."""
    lo = max(day_lo, acct.signup_day, 0)
    if lo >= day_hi:
        return
    for _ in range(n):
        day = rng.randrange(lo, day_hi)
        merchant_id = _pick_merchant(cfg, rng, acct, merchants, pop_weights)
        mu, sigma = CATEGORIES[by_id[merchant_id].category]
        failed = rng.random() < acct.failure_rate
        # Refund roll drawn unconditionally, THEN gated by `failed` -- not
        # `0 if failed else rng.random()...`, which skips the draw entirely
        # when failed is True. Since `failed` itself depends on
        # acct.failure_rate, and failure_rate now differs by ring type
        # (Task 3's refund-abuse mechanism), a short-circuited draw would make
        # the main stream's word count depend on which ring type an account
        # belongs to -- the exact isolation trap this module's docstring
        # warns about, just one level further down than the ring injector.
        refund_roll = rng.random() < acct.refund_rate
        out.append(
            Txn(
                txn_id=f"t{len(out):06d}",
                ts_minute=_timestamp(rng, day),
                account_id=acct.account_id,
                device_id=_pick_device(cfg, rng, acct),
                ip_id=_pick_ip(cfg, rng, acct, nat_ips),
                instrument_id=rng.choice(acct.instruments),
                merchant_id=merchant_id,
                amount=round(rng.lognormvariate(mu, sigma) * acct.amount_mult, 2),
                status="failed" if failed else "captured",
                is_refund=0 if failed else int(refund_roll),
                account_age_days=day - acct.signup_day,
            )
        )


# --------------------------------------------------------------------------
# injectors
# --------------------------------------------------------------------------
#
# Both injectors assign every cluster an `active_period` and confine all of its
# activity to that period's day range. This is what makes the ring-level split
# in split.py *possible* rather than best-effort: a ring cannot straddle two
# splits if it never transacted outside one period.


def _period_days(cfg: Config, period: str) -> tuple[int, int]:
    return cfg.split_boundaries[period]


RING_TYPES: tuple[str, ...] = ("device", "ip", "instrument", "refund", "hybrid")

# Dedicated-stream primes for the four new ring mechanisms (Tier 1). The four
# primes already in use below -- 49_979_687, 15_485_863, 32_452_843, 1_000_003
# -- belong to the pre-existing device-ring / family injectors and are never
# reused. These four are new and distinct (verified prime, and distinct from
# the first four -- see task-3-report.md).
_TYPE_SIGNUP_PRIME = 67_867_967       # non-device ring types' signup-day draw
_INSTRUMENT_POOL_PRIME = 86_028_121   # instrument concentration (instrument & hybrid)
_REFUND_RATE_PRIME = 104_395_301      # refund-abuse elevated refund/failure rate
_REFUND_MERCHANT_PRIME = 122_949_823  # refund-abuse merchant-pool concentration


def _ring_type_plan(cfg: Config) -> list[str]:
    """Which of the five mechanisms each ring index gets.

    Pure counts, zero RNG calls -- the plan itself cannot perturb anything
    drawn afterward, however the type MIX changes. Ordered in fixed blocks
    (all device rings, then all ip rings, ...) rather than shuffled, so that
    changing one type's count only ever shifts the ring INDICES of the types
    that come after it in this tuple, never the ones before.
    """
    counts = {
        "device": cfg.n_rings_device,
        "ip": cfg.n_rings_ip,
        "instrument": cfg.n_rings_instrument,
        "refund": cfg.n_rings_refund,
        "hybrid": cfg.n_rings_hybrid,
    }
    plan: list[str] = []
    for t in RING_TYPES:
        plan.extend([t] * counts[t])
    return plan


def _inject_rings(
    cfg: Config, rng: random.Random, merchants: list[Merchant], pop_weights: list[float],
    start_idx: int,
) -> list[Account]:
    """Five ring mechanisms, one injector.

    **device** -- the original Tier 0 mechanism, unchanged: members route most
    (not all) traffic through one or two shared devices, with partial card
    overlap (or, for a pool-funded fraction, a small shared-card pool -- Phase
    10's `is_hybrid_funded`), an elevated refund/failure rate, and usually a
    coordinated burst.

    **ip** -- members converge on one non-common IP instead of a device. Gives
    `ip_sharing` (config.py) something to measure for the first time.

    **instrument** -- a small shared-instrument pool, same mule mechanic as
    the device type's pool-funding branch, but WITHOUT device convergence:
    members keep their own home/secondary devices.

    **refund** -- behaviourally defined: elevated refund/failure rate and
    merchant concentration (a small cash-out pool), with no device/IP/
    instrument convergence at all -- weak-to-absent infrastructure sharing.

    **hybrid** -- device + IP + instrument sharing together, the genuinely
    multi-attribute case. (Not the same thing as the device type's own
    `is_hybrid_funded` sub-variant, which only swaps instrument funding.)

    Every "usually"/"most, not all" here is deliberate, same as Tier 0: a
    mechanism that always converges on everything is separable by a single
    rule, and a benchmark a single rule solves measures nothing.

    RNG isolation. Every draw on the shared `rng` below (`size`,
    `base_refund_rate`, `bursts`, `is_hybrid_funded`, the `sharers` sample) runs
    UNCONDITIONALLY, once per ring, in the same order and over the same-width
    range regardless of which of the five types that ring index is -- only
    which mechanism's code path actually USES the result differs. Every
    mechanism-specific decoration (which attribute converges, at what rate, on
    which pool) is drawn from a `random.Random` dedicated to that ring and that
    mechanism, so it can never perturb `rng` at all. The one thing that still
    needs care even on a dedicated stream: `rng.choice(acct.instruments)` and
    `rng.choice(acct.merchants)` run later, on the SHARED stream, during
    emission -- and `_randbelow`'s rejection sampling spends words on a list's
    LENGTH, not its content. So every mechanism below REPLACES a list's
    contents (from its own dedicated stream) without ever changing how many
    elements it has.
    """
    periods = list(cfg.split_boundaries)
    plan = _ring_type_plan(cfg)
    out: list[Account] = []
    idx = start_idx

    for r, ring_type in enumerate(plan):
        period = periods[r % len(periods)]  # round-robin: every split gets rings
        day_lo, day_hi = _period_days(cfg, period)
        size = rng.randint(cfg.ring_size_min, cfg.ring_size_max)
        ring_id = f"ring{r:02d}"
        base_refund_rate = rng.uniform(cfg.ring_refund_rate_min, cfg.ring_refund_rate_max)
        bursts = rng.random() >= cfg.p_ring_no_burst
        # Phase 10, device type only: a fraction of DEVICE rings are pool-
        # funded instead of partial-overlap. Drawn for every ring, every type,
        # so a non-device ring's presence at this index never changes whether
        # this word gets consumed -- see the isolation note above.
        is_hybrid_funded = (cfg.ring_instrument_pool_size > 0
                            and rng.random() < cfg.p_ring_instrument_funded)
        # Dedicated per-ring streams. Constructed for every ring regardless of
        # type -- cheap, and it keeps "which streams exist" independent of the
        # type mix too.
        signup_rng = random.Random(cfg.seed * 49_979_687 + r)
        type_signup_rng = random.Random(cfg.seed * _TYPE_SIGNUP_PRIME + r)

        if ring_type == "refund":
            rate_rng = random.Random(cfg.seed * _REFUND_RATE_PRIME + r)
            refund_rate = rate_rng.uniform(cfg.refund_ring_rate_min, cfg.refund_ring_rate_max)
            failure_rate = cfg.refund_ring_failure_rate
        else:
            refund_rate = base_refund_rate
            failure_rate = cfg.ring_failure_rate

        members: list[Account] = []
        for _ in range(size):
            if ring_type == "device":
                # Unchanged from Tier 0: thin-history mules, except a
                # pool-funded ring's mix of fresh mules and older
                # compromised/synthetic accounts (Phase 10, README finding #1).
                signup_day = (
                    day_lo - signup_rng.randint(cfg.ring_hybrid_signup_min_days,
                                                cfg.ring_hybrid_signup_max_days)
                    if is_hybrid_funded else
                    day_lo - signup_rng.randint(1, 20)
                )
            else:
                # The four new types get the same thin-history-by-default,
                # sometimes-older mix, on their OWN dedicated stream so it
                # cannot perturb the device type's signup_rng or the main
                # stream. Keeps account_newness from becoming a perfect
                # ring/non-ring separator now that most rings are young.
                widen = type_signup_rng.random() < cfg.ring_type_old_signup_fraction
                signup_day = (
                    day_lo - type_signup_rng.randint(cfg.ring_hybrid_signup_min_days,
                                                     cfg.ring_hybrid_signup_max_days)
                    if widen else
                    day_lo - type_signup_rng.randint(1, 20)
                )
            acct = _new_account(cfg, rng, idx, merchants, pop_weights,
                                signup_day=signup_day, kind="ring")
            idx += 1
            acct.active_period = period
            acct.ring_id = ring_id
            acct.ring_type = ring_type
            acct.refund_rate = refund_rate
            acct.failure_rate = failure_rate
            acct.extra["burst"] = float(bursts)
            if ring_type == "device":
                acct.shared_device = f"d_ring{r:02d}"
                acct.extra["shared_device_share"] = cfg.ring_shared_device_share
            members.append(acct)

        # Unconditional every ring, every type -- see isolation note. Applied
        # below only for ring_type == "device", same as before Phase 10.
        sharers = rng.sample(members, min(len(members), rng.randint(2, 3)))
        if cfg.ring_instrument_share > 0:
            share_rng = random.Random(cfg.seed * 15_485_863 + r)
            sharers = share_rng.sample(
                members,
                min(len(members),
                    max(2, round(cfg.ring_instrument_share * len(members)))),
            )
        shared_pi = f"pi_{ring_id}"

        if ring_type == "device":
            if is_hybrid_funded:
                pool_rng = random.Random(cfg.seed * 32_452_843 + r)
                pool = [
                    f"pi_{ring_id}_f{j}"
                    for j in range(min(cfg.ring_instrument_pool_size, len(members)))
                ]
                for acct in members:
                    acct.instruments = [pool_rng.choice(pool)]  # length-preserving: 1 -> 1
            else:
                for acct in sharers:
                    acct.instruments.append(shared_pi)

        elif ring_type == "ip":
            for acct in members:
                acct.shared_ip = f"ip_ring{r:02d}"
                acct.extra["shared_ip_share"] = cfg.ring_shared_ip_share

        elif ring_type == "instrument":
            instr_rng = random.Random(cfg.seed * _INSTRUMENT_POOL_PRIME + r)
            pool = [
                f"pi_{ring_id}_i{j}"
                for j in range(min(cfg.ring_type_instrument_pool_size, len(members)))
            ]
            for acct in members:
                acct.instruments = [instr_rng.choice(pool)]  # length-preserving: 1 -> 1

        elif ring_type == "refund":
            merch_rng = random.Random(cfg.seed * _REFUND_MERCHANT_PRIME + r)
            pool = merch_rng.sample(
                [m.merchant_id for m in merchants],
                min(cfg.refund_ring_merchant_pool_size, len(merchants)),
            )
            # Length-preserving: replace CONTENT, keep each member's own
            # merchants-list length, so the later `rng.choice(acct.merchants)`
            # in _add_burst/_emit consumes the same number of words regardless
            # of which ring type this index turned out to be.
            for acct in members:
                acct.merchants = [merch_rng.choice(pool) for _ in acct.merchants]
            # Weak partial instrument overlap -- same 2-3-sharer mechanism the
            # device type's own non-pool-funded branch uses below, reusing the
            # `sharers`/`shared_pi` draws that already happen unconditionally
            # for every ring (see the isolation note above), so this needs no
            # new randomness. Without ANY structural edge, a refund ring has
            # zero shared device/ip/instrument accounts and graph.py forms no
            # component at all -- the ring reduces to singletons and is never
            # scored (review finding, Task 3 fix-up). "Weak-to-absent"
            # infrastructure sharing means weak, not literally none: enough of
            # an edge to exist as a candidate component, not enough to be easy.
            for acct in sharers:
                acct.instruments.append(shared_pi)

        elif ring_type == "hybrid":
            instr_rng = random.Random(cfg.seed * _INSTRUMENT_POOL_PRIME + r)
            pool = [
                f"pi_{ring_id}_h{j}"
                for j in range(min(cfg.ring_type_instrument_pool_size, len(members)))
            ]
            for acct in members:
                acct.shared_device = f"d_ring{r:02d}"
                acct.extra["shared_device_share"] = cfg.ring_shared_device_share
                acct.shared_ip = f"ip_ring{r:02d}"
                acct.extra["shared_ip_share"] = cfg.ring_shared_ip_share
                acct.instruments = [instr_rng.choice(pool)]  # length-preserving: 1 -> 1

        out.extend(members)

    return out


def _inject_families(
    cfg: Config, rng: random.Random, merchants: list[Merchant], pop_weights: list[float],
    start_idx: int,
) -> list[Account]:
    """Family clusters: the Tier 0 hard negative.

    A family shares a household device *and* a home IP *and* often a card -- the
    same structural attributes a ring shares. That is the whole point: if the
    hard negative did not overlap the ring on structure, it would be an easy
    negative and would prove nothing about false-positive resistance.

    What differs is behaviour: long tenure (they registered long before the
    window), activity spread evenly across their period, diverse merchants, and
    no coordinated burst -- except for the households that genuinely do transact
    together in one evening, which is why `family_coburst_rate` exists.
    """
    periods = list(cfg.split_boundaries)
    out: list[Account] = []
    idx = start_idx

    for f in range(cfg.n_families):
        period = periods[f % len(periods)]
        cluster_id = f"fam{f:02d}"
        household_device = f"d_fam{f:02d}"
        household_ip = f"ip_fam{f:02d}"
        shares_card = rng.random() < cfg.p_family_shared_instrument
        shared_pi = f"pi_{cluster_id}"
        refund_rate = rng.uniform(cfg.base_refund_rate, cfg.family_refund_rate_max)
        cobursts = rng.random() < cfg.family_coburst_rate
        size = rng.randint(cfg.family_size_min, cfg.family_size_max)

        # The household's regular shops. Members draw part of their preferences
        # from here, so they coincide on a merchant more often than strangers do
        # -- but not always, and not at a single agreed minute the way a ring
        # does. Empty pool when overlap is 0, which is the pre-E3 behaviour.
        # Drawn from a DEDICATED per-cluster generator, not the main stream. The
        # first attempt used `rng` and silently re-rolled every subsequent draw,
        # which moved signals that merchant preferences cannot possibly affect
        # (instrument_sharing by +0.070). An experiment that perturbs the shared
        # random stream is not isolated, whatever its headline number says.
        household_pool: list[str] = []
        pool_rng = random.Random(cfg.seed * 1_000_003 + f)
        if cfg.family_merchant_overlap > 0:
            for m in pool_rng.choices(merchants, weights=pop_weights,
                                      k=cfg.family_merchant_pool_size * 3):
                if m.merchant_id not in household_pool:
                    household_pool.append(m.merchant_id)
                if len(household_pool) == cfg.family_merchant_pool_size:
                    break

        for _ in range(size):
            acct = _new_account(
                cfg, rng, idx, merchants, pop_weights,
                # long-standing customers: real tenure, unlike ring mules
                signup_day=-rng.randint(cfg.family_signup_min_days,
                                        cfg.family_signup_max_days),
                kind="family",
            )
            idx += 1
            acct.active_period = period
            acct.cluster_id = cluster_id
            acct.home_device = household_device
            acct.home_ip = household_ip
            acct.refund_rate = refund_rate
            acct.extra["coburst"] = float(cobursts)
            if household_pool:
                n_shared = max(1, round(cfg.family_merchant_overlap * len(acct.merchants)))
                shared = pool_rng.sample(household_pool,
                                         min(n_shared, len(household_pool)))
                personal = [m for m in acct.merchants if m not in shared]
                acct.merchants = (shared + personal)[: len(acct.merchants)]
            if shares_card:
                acct.instruments.append(shared_pi)
            out.append(acct)

    return out


def _add_burst(
    cfg: Config, rng: random.Random, members: list[Account], window_minutes: int,
    participation: float, by_id: dict[str, Merchant],
    nat_ips: list[str], out: list[Txn], shared_merchant: bool = True,
) -> None:
    """A cluster of accounts hitting one merchant inside a short window.

    Used for both the ring burst and the milder family co-purchase evening, with
    different windows and participation rates -- same mechanism, so the scorer
    cannot separate them by anything except degree.
    """
    if not members:
        return
    day_lo, day_hi = _period_days(cfg, members[0].active_period)
    # `shared_merchant` is the whole difference between a ring and a household.
    # A ring converges on one merchant AND one window; a household shares only
    # the window, because its members happen to be awake at the same time.
    shared_id = rng.choice(members[0].merchants)
    burst_day = rng.randrange(day_lo, day_hi)
    base = _timestamp(rng, burst_day)

    for acct in members:
        if rng.random() >= participation:
            continue
        for _ in range(rng.randint(1, 2)):
            merchant_id = shared_id if shared_merchant else rng.choice(acct.merchants)
            mu, sigma = CATEGORIES[by_id[merchant_id].category]
            failed = rng.random() < acct.failure_rate
            # See the matching comment in _emit: draw unconditionally, gate
            # after, so word count does not depend on acct.failure_rate.
            refund_roll = rng.random() < acct.refund_rate
            out.append(
                Txn(
                    txn_id=f"t{len(out):06d}",
                    ts_minute=base + rng.randrange(window_minutes),
                    account_id=acct.account_id,
                    device_id=_pick_device(cfg, rng, acct),
                    ip_id=_pick_ip(cfg, rng, acct, nat_ips),
                    instrument_id=rng.choice(acct.instruments),
                    merchant_id=merchant_id,
                    amount=round(rng.lognormvariate(mu, sigma) * acct.amount_mult, 2),
                    status="failed" if failed else "captured",
                    is_refund=0 if failed else int(refund_roll),
                    account_age_days=burst_day - acct.signup_day,
                )
            )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def generate(cfg: Config) -> tuple[list[Txn], list[Label]]:
    """Build the whole synthetic population and its ground truth.

    Returns two independent lists. The transactions carry no labels; the labels
    carry no behaviour. Keeping them apart at the type level is the cheapest
    defence against the leakage this benchmark is supposed to rule out.
    """
    rng = random.Random(cfg.seed)

    merchants = _build_merchants(cfg, rng)
    pop_weights = [m.popularity for m in merchants]
    by_id = {m.merchant_id: m for m in merchants}
    nat_ips = _build_nat_ips(cfg)

    background = _build_background(cfg, rng, merchants, pop_weights)
    rings = _inject_rings(cfg, rng, merchants, pop_weights, len(background))
    families = _inject_families(cfg, rng, merchants, pop_weights,
                               len(background) + len(rings))
    accounts = background + rings + families

    txns: list[Txn] = []

    # Background accounts span the whole window; labelled accounts stay inside
    # their assigned period, which is what keeps rings and clusters split-safe.
    for acct in background:
        n = max(1, round(rng.lognormvariate(1.5, 0.7)))
        # A contiguous activity spell rather than uniform lifetime traffic. Real
        # accounts have spells, and it is what spreads unlabelled components
        # across all three splits instead of piling them into train (bugs.md B1).
        span = rng.randint(cfg.bg_active_days_min, cfg.bg_active_days_max)
        start = rng.randrange(0, cfg.days)
        _emit(cfg, rng, acct, start, min(cfg.days, start + span), n,
              merchants, pop_weights, by_id, nat_ips, txns)

    for acct in rings:
        day_lo, day_hi = _period_days(cfg, acct.active_period)
        _emit(cfg, rng, acct, day_lo, day_hi, rng.randint(6, 12),
              merchants, pop_weights, by_id, nat_ips, txns)

    for acct in families:
        day_lo, day_hi = _period_days(cfg, acct.active_period)
        _emit(cfg, rng, acct, day_lo, day_hi, rng.randint(8, 16),
              merchants, pop_weights, by_id, nat_ips, txns)

    # Coordinated activity, added after the ordinary traffic it hides in.
    for ring_id in sorted({a.ring_id for a in rings}):
        members = [a for a in rings if a.ring_id == ring_id]
        if members[0].extra.get("burst", 0.0):
            _add_burst(cfg, rng, members, cfg.ring_burst_minutes,
                       cfg.ring_burst_participation, by_id, nat_ips, txns)

    for cluster_id in sorted({a.cluster_id for a in families}):
        members = [a for a in families if a.cluster_id == cluster_id]
        if members[0].extra.get("coburst", 0.0):
            _add_burst(cfg, rng, members,
                       cfg.ring_burst_minutes * cfg.family_coburst_window_multiplier,
                       cfg.family_coburst_participation, by_id, nat_ips, txns,
                       shared_merchant=cfg.family_coburst_shared_merchant)

    txns.sort(key=lambda t: (t.ts_minute, t.account_id))
    txns = [t._replace(txn_id=f"t{i:06d}") for i, t in enumerate(txns)]

    labels = [
        Label(a.account_id, a.ring_id, a.cluster_id, a.active_period, a.ring_type)
        for a in accounts
    ]
    return txns, labels


def accounts_per_attribute(txns: list[Txn], attr: str) -> dict[str, int]:
    """Distinct accounts touching each value of `attr` -- the reuse distribution.

    Shared by the self-check here, the hygiene caps in graph.py and the reuse
    histograms in the integrity report, so all three agree by construction.
    """
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for t in txns:
        key = (getattr(t, attr), t.account_id)
        if key in seen:
            continue
        seen.add(key)
        counts[key[0]] = counts.get(key[0], 0) + 1
    return counts


if __name__ == "__main__":
    from collections import Counter

    cfg = Config()
    txns, labels = generate(cfg)

    per_device = accounts_per_attribute(txns, "device_id")
    per_ip = accounts_per_attribute(txns, "ip_id")
    nat_counts = [c for ip, c in per_ip.items() if ip.startswith("ip_nat")]
    floor = cfg.max_ip_degree * cfg.nat_common_infra_margin

    assert 0.9 * cfg.target_txns <= len(txns) <= 1.1 * cfg.target_txns, len(txns)
    assert Counter(per_device.values())[1] > 0.7 * len(per_device), "device reuse too high"
    assert min(nat_counts) > floor, f"NAT IPs not common enough: {min(nat_counts)} <= {floor}"
    assert all(t.txn_id and t.ts_minute >= 0 for t in txns)

    print(f"transactions       {len(txns)}")
    print(f"accounts           {len(labels)}")
    print(f"devices            {len(per_device)}")
    print(f"accts/device dist  {sorted(Counter(per_device.values()).items())}")
    print(f"NAT ip accounts    min={min(nat_counts)} max={max(nat_counts)} (cap {cfg.max_ip_degree})")
    print(f"ring accounts      {sum(1 for l in labels if l.ring_id)}")
    print(f"family accounts    {sum(1 for l in labels if l.cluster_id)}")
    print("phase 2-3 checks ok")

