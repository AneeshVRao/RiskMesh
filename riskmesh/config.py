"""Every knob in the RiskMesh Tier 0 benchmark, in one frozen dataclass.

Nothing else in the package reads a module-level constant. Everything takes a
`Config`, which is what makes a parameter sweep possible later without a
refactor, and what makes `fingerprint()` a complete description of a run.

Reproducibility note: CPython guarantees only that `Random.random()` reproduces
the same sequence across versions for a given seed. Higher-level helpers
(`shuffle`, `sample`, `gauss`, ...) may change between versions. The generator
uses them anyway because they are far clearer, so determinism here is scoped to
*one interpreter version* — which is why the integrity report records
`sys.version` alongside the seed. Two runs on the same Python are byte-identical;
that is the claim the tests make and the only one we make.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# The eight deterministic signals, in report order.
#
# `temporal_burst` carries the largest weight because coordination in time was
# expected to separate a ring from a family sharing one device. Measurement says
# otherwise: ring 0.344 vs family 0.352 normalised, so it separates rings from
# background and NOT from the hard negatives. The weight is unchanged pending
# RISK-003; the justification is corrected here rather than left standing as a
# claim the data contradicts. The signals that do discriminate ring from family
# are account_newness (+0.882), failure_refund_rate (+0.139), device_sharing
# (+0.114).
SIGNALS: tuple[str, ...] = (
    "device_sharing",
    "temporal_burst",
    "instrument_sharing",
    "instrument_pool_concentration",
    "failure_refund_rate",
    "ip_sharing",
    "account_newness",
    "merchant_concentration",
)


def _default_weights() -> dict[str, float]:
    """Tier 0 weights -- Phase 11 re-freeze: D_drop_flagged, not A_baseline.

    `ip_sharing` carries 0.00 because the Tier 0 generator places no ring
    information in the IP dimension at all: max-accounts-on-one-non-common-IP is
    exactly 1.00 for every ring component AND every background component, while
    family clusters average 4.94. The signal cannot separate positives from the
    bulk of negatives here, and at its old +0.10 it subtracted 0.0378 from a
    total positive-vs-negative score separation of 0.2009 -- degrading the
    scorer by ~19%. It stays computed, as investigator evidence and because it
    is the right definition once Tier 1 adds a shared-IP ring type; it simply
    contributes nothing until it has something to say. See bugs.md RISK-001.

    `instrument_sharing` and `merchant_concentration` ALSO carry 0.00, as of
    Phase 11. `weight_search_protocol.md`'s re-run (after Phase 10's hybrid
    pool-funded ring type and the new `instrument_pool_concentration` signal)
    found `D_drop_flagged` -- which zeros exactly these two, RISK-004's and
    RISK-002's flagged signals -- tying `A_baseline` on validation expected
    loss (8,849.98, identical confusion matrix) and winning the tie-break on
    `positives_below_max_negative` (0.625 vs 0.5625). Per the protocol's own
    "the one subtlety" clause, `A_baseline` IS whatever this function returns,
    so the winner is folded back in here rather than left as a frozen record
    the pipeline does not actually use. Re-running the full search against
    THIS weight vector as the new `A_baseline` reproduces the same winner
    (fixed point reached in one extra iteration) -- see
    `weight_search_protocol.md` Section 8.

    The remaining five keep their Tier 0 baseline ratios, renormalised to
    1.00, so zeroing three signals does not silently re-rank the other five.
    """
    active = {
        "device_sharing": 0.22,
        "temporal_burst": 0.25,
        "instrument_pool_concentration": 0.12,
        "failure_refund_rate": 0.12,
        "account_newness": 0.10,
    }
    total = sum(active.values())
    weights = {name: value / total for name, value in active.items()}
    weights["ip_sharing"] = 0.0
    weights["instrument_sharing"] = 0.0
    weights["merchant_concentration"] = 0.0
    return weights


@dataclass(frozen=True)
class Config:
    """Generator, graph, scorer and benchmark parameters for one run."""

    # --- reproducibility -------------------------------------------------
    seed: int = 20260824

    # --- population ------------------------------------------------------
    n_accounts: int = 520  # background population; ring/family accounts are extra
    n_merchants: int = 40
    n_nat_ips: int = 20
    target_txns: int = 5000
    # NAT reuse is emergent from p_nat_ip rather than a fixed per-IP account
    # count. What has to hold is that every NAT IP lands far above max_ip_degree
    # so hygiene actually caps it -- that is the property the tests check.
    nat_common_infra_margin: float = 3.0

    # Background accounts transact in a contiguous spell, not uniformly across
    # the whole window. Without this every background component's median
    # timestamp lands mid-window (i.e. in train) and the test split ends up with
    # no unlabelled negatives at all -- see B1 in bugs.md.
    bg_active_days_min: int = 4
    bg_active_days_max: int = 20

    # Unlabelled background sharing. Without this, "two accounts share a device"
    # separates the classes perfectly and the whole benchmark is worthless.
    n_noise_shared_devices: int = 70
    n_noise_shared_instruments: int = 20

    # --- normal behaviour mix (must each sum to 1.0 where they partition) --
    p_home_device: float = 0.90
    p_home_ip: float = 0.70
    p_nat_ip: float = 0.25
    p_sticky_merchant: float = 0.80
    base_refund_rate: float = 0.02
    base_failure_rate: float = 0.04

    # --- time window -----------------------------------------------------
    days: int = 30
    train_days: int = 18
    val_days: int = 6
    test_days: int = 6

    # --- ring injector (shared device only, Tier 0) ----------------------
    n_rings: int = 24  # 8 per split: 4 was too coarse to report metrics on
    ring_size_min: int = 4
    ring_size_max: int = 9
    # How many of a ring's members share one instrument, as a fraction of ring
    # size. 0.0 keeps the original behaviour -- a flat 2-3 sharers however large
    # the ring is -- which is RISK-004: a 9-member household's shared card
    # reaches all 9, a 9-member ring's reaches 3, so the household scores higher
    # on instrument_sharing than the ring does. Experiment E4 sets 0.5.
    # Deliberately bounded well below 1.0: a real mule ring would concentrate
    # harder than any household, but a ring that always shares one card across
    # every member is separable by a single rule.
    ring_instrument_share: float = 0.0
    # --- hybrid pool-funded rings (Phase 10) ------------------------------
    # A fraction of the existing shared-device rings additionally fund every
    # member through a small pool of instruments (replacing personal cards
    # entirely) instead of the flat 2-3-sharer partial overlap, AND draw signup
    # age from a much wider range. This is RISK-004's rejected experiment E6,
    # reused as a real second ring mechanism instead of an inert toggle: E6 was
    # rejected only for over-separating a benchmark whose only positive class
    # was the device ring; applied to a MINORITY of rings alongside the
    # majority untouched, it should not have that failure mode. See bugs.md
    # RISK-004 "closed... A future funding-network ring type should restart
    # from experiment_e6.json".
    #
    # The wide signup range is what breaks the account-age confound recorded
    # in README.md finding #1: a hybrid ring's members are a mix of fresh
    # mules and older compromised/synthetic accounts, so "account age <= 30
    # days" stops being a perfect ring classifier.
    # 0.4 (the initial candidate) failed the Tier-1 difficulty gate on
    # train+validation: positives_below_max_negative 0.3125 against a required
    # >= 0.45. Tuned up against the panel per the project's "tune config,
    # don't add realism" discipline (task_today.md Step 1) -- 0.7 clears both
    # Tier-1 gates with margin (positives_below_max_negative 0.5625, hard
    # negatives inside positive range 9) without approaching 1.0, where the
    # panel starts to FAIL outright (E6's over-separation failure mode).
    p_ring_instrument_funded: float = 0.7  # fraction of rings that are hybrid
    ring_hybrid_signup_min_days: int = 5
    ring_hybrid_signup_max_days: int = 400
    ring_shared_device_share: float = 0.68  # not 1.0 -- members keep own traffic
    ring_burst_minutes: int = 30
    ring_failure_rate: float = 0.15
    # Overlap knobs. These exist so the benchmark can be tuned back inside its
    # non-triviality bounds by changing a number, never by adding new realism --
    # see the Tier 0 time cap in implementation_plan.md.
    ring_burst_participation: float = 0.75  # not every member joins the burst
    p_ring_no_burst: float = 0.30           # some rings never burst at all
    ring_refund_rate_min: float = 0.01      # per-ring refund rate is a range,
    ring_refund_rate_max: float = 0.25      # not one give-away constant

    # --- family hard negative --------------------------------------------
    # Same structural attributes as a ring (shared device + shared IP, sometimes
    # a shared instrument); different behaviour. That is what makes it hard.
    n_families: int = 24
    family_size_min: int = 2
    family_size_max: int = 8  # large households share a device as widely as a
                              # ring does -- this is what stops the device-only
                              # baseline from separating the classes by itself
    p_family_shared_instrument: float = 0.5
    # A household really does sometimes transact together in one evening, and a
    # returns-heavy household really does refund a lot. Both overlap the ring
    # signals on purpose -- that is what makes these hard negatives.
    family_coburst_rate: float = 0.60
    family_coburst_participation: float = 0.9
    family_coburst_window_multiplier: int = 1
    # Whether a household's co-burst lands on ONE merchant (as a ring's does) or
    # each member goes to their own. True was the original behaviour and is why
    # temporal_burst could not tell a household from a ring (RISK-003). False is
    # experiment E2, ADOPTED: families share time because they share a household;
    # rings additionally converge on the same merchant. Do not flip this back
    # without re-reading the E1/E2/E3 records in bugs.md -- E1 (no household
    # co-burst at all) and E3 (overlapping household merchant pools) were both
    # measured and rejected, E1 for erasing the hard negative and E3 for
    # collapsing the non-triviality margin to 0.2500.
    family_coburst_shared_merchant: bool = False
    # How much of a household's merchant preferences are shared between its
    # members. 0.0 means each member shops entirely independently (E2); 1.0 would
    # make them shop identically, which is ring-like. A real household overlaps
    # partially -- same grocery and delivery app, different everything else.
    # Stays 0.0: E3 set it to 0.5 and was rejected. Kept as a knob because the
    # rejection is a measured result, not a dead end -- see bugs.md RISK-003.
    family_merchant_overlap: float = 0.0
    family_merchant_pool_size: int = 4
    family_refund_rate_max: float = 0.30
    # Not every household is a long-standing customer -- a family that just
    # joined looks young, exactly like a mule ring does. Keeping the range wide
    # is what stops account_newness separating the classes on its own.
    family_signup_min_days: int = 15
    family_signup_max_days: int = 540

    # --- graph hygiene ---------------------------------------------------
    # Caps sit well above realistic ring size (<= ring_size_max) so a real ring
    # is never capped away. Every capped node is listed in the integrity report.
    max_ip_degree: int = 8
    max_device_degree: int = 12
    # RISK-004 option 1, experiment E5. False keeps the original definition of
    # instrument_sharing -- max accounts on one instrument, normalised by the
    # global cap below -- which rewards raw group size and is why a household
    # outscores a ring. True measures what SHARE of a component's accounts sit
    # on its most-shared instrument, which is concentration rather than
    # headcount. Default False until an experiment is adopted.
    instrument_sharing_component_relative: bool = False
    # RISK-004 option 2, experiment E6, adopted in Phase 10 as a real (minority)
    # ring mechanism. A mule network is funded through a small pool of cards
    # used by many accounts; a household shares one card on top of everyone's
    # own. 0 disables the mechanism entirely. When > 0, every member of a ring
    # selected as hybrid (`p_ring_instrument_funded`) is funded through one card
    # drawn from a pool of this size, replacing their personal instrument --
    # non-hybrid rings are unaffected and keep the flat 2-3-sharer partial
    # overlap below. Scored by the always-on `instrument_pool_concentration`
    # signal in score.py, independent of `instrument_sharing_accounts_per_card`.
    # E6 itself was rejected as a benchmark-wide default (see bugs.md RISK-004)
    # for over-separating a benchmark whose only positive class was the device
    # ring; restricted to a majority-but-not-all fraction of rings (see
    # `p_ring_instrument_funded` above) it is the intended restart point. Pool
    # size 4 was chosen alongside that fraction, tuned against the
    # non-triviality panel per task_today.md Step 1.
    ring_instrument_pool_size: int = 4
    # The matching feature: accounts per distinct instrument in the component,
    # normalised by the same global cap every other signal uses -- measures how
    # few cards fund how many accounts, rather than how big the biggest sharing
    # set is. Deliberately NOT normalised by component size -- see bugs.md L1.
    instrument_sharing_accounts_per_card: bool = False
    max_instrument_degree: int = 9  # above family_size_max, so a genuine family
                                    # card is never mistaken for common infra
    min_edge_txns: int = 2

    # --- scorer ----------------------------------------------------------
    # ponytail: frozen=True blocks field *assignment* only -- cfg.weights["x"]=5
    # still mutates the dict, so fingerprint() describes the config as
    # constructed, not as later poked. Single-author benchmark, nobody pokes it.
    # Wrap in MappingProxyType if a sweep harness ever shares one Config.
    weights: dict[str, float] = field(default_factory=_default_weights)
    burst_window_minutes: int = 30

    # --- benchmark bounds (non-triviality) -------------------------------
    # Checked on train+val only; test statistics must never tune the generator.
    #
    # The overlap knobs above were selected by sweeping them against the
    # non-triviality panel and the VALIDATION threshold, never against test
    # metrics. Selection rule, stated so it can be argued with: among configs
    # whose panel verdict is PASS, prefer the widest margin on the honesty
    # checks, using validation F1 only to break ties. Maximising validation F1
    # instead picks a config that clears the bounds by a hair, which reads as a
    # better benchmark while being a more fragile one.
    min_positive_below_max_negative_fraction: float = 0.20
    max_shared_device_baseline_f1: float = 0.85
    single_signal_flag_f1: float = 0.95
    max_largest_component_share: float = 0.15
    # A weighted signal whose normalised mean is this much LOWER on positives
    # than on negatives is contributing in the wrong direction -- it is helping
    # the negatives. Reported as FLAG, not FAIL: see RISK-002.
    mis_signed_delta_tolerance: float = 0.02

    # --- evaluation ------------------------------------------------------
    # Tier 0 benchmark ground-truth rule: a component is positive iff this
    # fraction of its accounts belongs to a single injected ring. A labelling
    # convention for this benchmark, not a definition of a risk ring.
    positive_component_ring_fraction: float = 0.50

    def __post_init__(self) -> None:
        if set(self.weights) != set(SIGNALS):
            missing = set(SIGNALS) - set(self.weights)
            extra = set(self.weights) - set(SIGNALS)
            raise ValueError(f"weights must cover SIGNALS exactly ({missing=}, {extra=})")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"scorer weights must sum to 1.0, got {total!r}")
        if self.train_days + self.val_days + self.test_days != self.days:
            raise ValueError("train+val+test days must equal days")
        if self.ring_size_max > self.max_device_degree:
            raise ValueError("device cap would clip a legitimate ring")

    # --- derived ---------------------------------------------------------
    @property
    def split_boundaries(self) -> dict[str, tuple[int, int]]:
        """Day ranges per split, half-open, chronologically ordered."""
        train_end = self.train_days
        val_end = train_end + self.val_days
        return {
            "train": (0, train_end),
            "validation": (train_end, val_end),
            "test": (val_end, self.days),
        }

    def period_of_day(self, day: int) -> str:
        for name, (start, end) in self.split_boundaries.items():
            if start <= day < end:
                return name
        raise ValueError(f"day {day} outside the {self.days}-day window")

    def fingerprint(self) -> str:
        """Stable sha256 over every field, so numbers trace back to a config."""
        blob = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


if __name__ == "__main__":
    cfg = Config()
    assert abs(sum(cfg.weights.values()) - 1.0) < 1e-9
    assert cfg.fingerprint() == cfg.fingerprint()
    assert cfg.period_of_day(0) == "train"
    assert cfg.period_of_day(20) == "validation"
    assert cfg.period_of_day(29) == "test"
    print(f"config ok  seed={cfg.seed}  fingerprint={cfg.fingerprint()}")
