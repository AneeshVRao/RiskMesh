"""PRD rows 63 and 70 -- baseline sanity checks and leave-one-group-out ablation.

Both tables answer the same reviewer's question from opposite sides. The
baselines ask *would something much simpler have worked?*; the ablation asks
*which parts of this are load-bearing?* A benchmark that reports neither is
asserting its own value rather than showing it.

The protocol is the one the rest of Tier 0 already uses and is not relaxed here:
every configuration selects its own cutoff on **validation only**, freezes it,
and reads test exactly once. Twelve configurations, twelve independent freezes.
Reusing one configuration's threshold on another would silently leak the
comparison, which is why `_freeze_cutoff()` and `select_threshold()` both take
validation rows as their entire input and assert it.

Written after `implementation_plan.md` recorded what would be reported whichever
way the numbers land -- including the two readings that would be uncomfortable.
Nothing here re-selects a weight, threshold or band from a held-out read.
"""

from __future__ import annotations

import random
import sys

from .config import SIGNALS, Config
from .costmodel import _renormalised, rescore
from .evaluate import (
    Candidate,
    best_f1_with_direction,
    confusion,
    prf,
    ring_recovery,
    score_at,
    select_threshold,
)
from .generate import Label, Txn
from .graph import Graph

DESIGN_SPLITS = ("train", "validation")

# Naive per-transaction rule for the transaction-level baseline. Raw fields on
# the transaction itself; no shared-attribute counts, nothing from the graph.
TXN_LEVEL_AMOUNT_PERCENTILE = 0.95
TXN_LEVEL_YOUNG_ACCOUNT_DAYS = 30

# The PRD names five feature groups. Mapped onto the seven signals as a
# PARTITION -- every signal belongs to exactly one group, so "full minus each
# group in turn" covers the whole scorer with no signal ablated twice or never.
# The split is structural (what accounts share) against behavioural (how
# accounts act); merchant_concentration sits on the behavioural side because it
# describes where the money went, not what two accounts have in common. That is
# a grouping choice and is called one.
ABLATION_GROUPS: dict[str, tuple[str, ...]] = {
    "device": ("device_sharing",),
    "ip": ("ip_sharing",),
    "instrument": ("instrument_sharing",),
    "temporal": ("temporal_burst",),
    "behavioral_refund": ("failure_refund_rate", "account_newness",
                          "merchant_concentration"),
}


def _assert_partition() -> None:
    covered: list[str] = []
    for group in ABLATION_GROUPS.values():
        covered.extend(group)
    if sorted(covered) != sorted(SIGNALS):
        raise ValueError(
            f"ABLATION_GROUPS is not a partition of SIGNALS: covered={sorted(covered)}, "
            f"signals={sorted(SIGNALS)}. A signal in no group is never ablated and a "
            f"signal in two is ablated twice; either way the table lies about coverage."
        )


_assert_partition()


# --------------------------------------------------------------------------
# shared protocol
# --------------------------------------------------------------------------


def _hard_negative_view(cands: list[Candidate]) -> list[Candidate]:
    """Positives, plus only the negatives that carry a family cluster.

    Separating rings from unrelated background accounts is the easy half of the
    problem. Reporting it alongside the full-negative view keeps the gap between
    the two visible rather than implied.
    """
    return [c for c in cands if c.is_positive or c.has_family]


def _freeze_cutoff(validation: list[Candidate],
                   values: dict[str, float]) -> dict[str, float | str | int]:
    """Best cutoff AND direction on VALIDATION only.

    Takes validation rows as its whole input and asserts it, in the same shape
    as `select_threshold()` -- there is no parameter through which test data
    could reach it.

    Both directions, not just `>=`. RISK-001 is exactly the bug where a
    one-directional sweep reported an inverted signal as useless: `ip_sharing`
    is inverted in this benchmark, because a ring keeps separate IPs while a
    household shares the router. Sweeping one direction would report the
    shared-IP baseline as far weaker than it honestly is, which flatters the
    system it is meant to challenge.
    """
    assert all(c.split == "validation" for c in validation), (
        "_freeze_cutoff received non-validation candidates -- "
        "this would be cutoff fitting on held-out data"
    )
    f1, direction, cut = best_f1_with_direction(
        [values[c.component_id] for c in validation],
        [c.is_positive for c in validation],
    )
    return {"cutoff": round(cut, 6), "direction": direction,
            "validation_f1": f1, "validation_components": len(validation)}


def _read_once(test: list[Candidate], values: dict[str, float],
               cutoff: float, direction: str) -> dict[str, float | int]:
    """Apply a frozen cutoff to the held-out split. Selects nothing."""
    assert all(c.split == "test" for c in test), "_read_once got non-test candidates"
    flags = [
        (values[c.component_id] >= cutoff if direction == ">="
         else values[c.component_id] <= cutoff, c.is_positive)
        for c in test
    ]
    counts = confusion(flags)
    return {**counts, **prf(counts)}


# --------------------------------------------------------------------------
# row 63 -- baselines
# --------------------------------------------------------------------------


def random_scores(cfg: Config, cands: list[Candidate]) -> dict[str, float]:
    """A score per component from a generator keyed on the component id.

    Keyed rather than drawn from one stream on purpose: a stream would make the
    result depend on iteration order, and this file has to reproduce
    byte-for-byte like every other artifact.
    """
    return {c.component_id: random.Random(f"{cfg.seed}:{c.component_id}").random()
            for c in cands}


def transaction_level_scores(
    txns: list[Txn], graph: Graph, design_ids: set[str],
    young_days: int = TXN_LEVEL_YOUNG_ACCOUNT_DAYS,
) -> tuple[dict[str, float], float]:
    """Fraction of a component's transactions that a naive per-transaction rule flags.

    The control that matters most, because it is the one a reviewer asks first:
    *would a transaction-level model have found these anyway?* A transaction is
    flagged when it is a refund or a failure, or its amount is at or above the
    95th percentile, or the account is young. Every input is a field on the
    transaction itself -- no shared-attribute counts, nothing from the graph
    beyond which transactions are being averaged over.

    The amount percentile is computed on **train+validation transactions only**.
    Taking it over the whole stream would leak the held-out split's amount
    distribution into the baseline, which is the same mistake as fitting a
    threshold on test, one layer down.
    """
    design_accounts: set[str] = set()
    for comp in graph.components:
        if comp.component_id in design_ids:
            design_accounts |= comp.accounts

    amounts = sorted(t.amount for t in txns if t.account_id in design_accounts)
    if not amounts:
        raise ValueError("no design transactions -- the amount cutoff is undefined")
    cutoff = amounts[min(len(amounts) - 1,
                         int(TXN_LEVEL_AMOUNT_PERCENTILE * (len(amounts) - 1)))]

    scores: dict[str, float] = {}
    for comp in graph.components:
        flagged = sum(
            1 for t in comp.txns
            if t.is_refund or t.status == "failed" or t.amount >= cutoff
            or t.account_age_days <= young_days
        )
        scores[comp.component_id] = round(flagged / max(1, len(comp.txns)), 6)
    return scores, round(cutoff, 2)


AGE_CUT_SENSITIVITY = (10, 20, 30, 45, 60, 90, 180)


def age_cut_sensitivity(txns: list[Txn], graph: Graph, design_ids: set[str],
                        validation: list[Candidate]) -> dict[str, float]:
    """Validation F1 of the transaction-level rule at several account-age cuts.

    30 days was fixed in `implementation_plan.md` before any of this ran, but a
    constant sitting neatly between two classes invites the question anyway.
    Answered on VALIDATION rows only, so it costs no held-out read and cannot
    become a back door to tuning the baseline on test.
    """
    out: dict[str, float] = {}
    for days in AGE_CUT_SENSITIVITY:
        values, _ = transaction_level_scores(txns, graph, design_ids, young_days=days)
        out[str(days)] = float(_freeze_cutoff(validation, values)["validation_f1"])
    return out


def baseline_report(cfg: Config, txns: list[Txn], graph: Graph,
                    cands: list[Candidate]) -> dict:
    """The five baselines PRD row 63 requires, each frozen then read once."""
    validation = [c for c in cands if c.split == "validation"]
    test = [c for c in cands if c.split == "test"]
    design_ids = {c.component_id for c in cands if c.split in DESIGN_SPLITS}
    txn_level, amount_cutoff = transaction_level_scores(txns, graph, design_ids)

    # Four challengers sweep their own cutoff over observed values. The shipped
    # scorer does NOT -- see below.
    specs: list[tuple[str, str, str, dict[str, float]]] = [
        ("random", "none",
         "A score per component from a seeded generator. The floor any real "
         "detector has to clear.",
         random_scores(cfg, cands)),
        ("shared_device_only", "one rule",
         "Accounts on the most-shared device. The single rule most likely to "
         "make the graph score redundant.",
         {c.component_id: c.raw_signals["device_sharing"] for c in cands}),
        ("shared_ip_only", "one rule",
         "Accounts on the most-shared non-common IP. Inverted in this "
         "benchmark: households share a router, rings do not.",
         {c.component_id: c.raw_signals["ip_sharing"] for c in cands}),
        ("transaction_level", "none",
         f"Fraction of the component's transactions flagged by refund, failure, "
         f"amount >= {amount_cutoff:.2f} (95th pct on design rows), or account "
         f"age <= {TXN_LEVEL_YOUNG_ACCOUNT_DAYS}d.",
         txn_level),
    ]

    rows = []
    for name, graph_use, blurb, values in specs:
        frozen = _freeze_cutoff(validation, values)
        cut, direction = float(frozen["cutoff"]), str(frozen["direction"])
        rows.append({
            "baseline": name,
            "uses_graph": graph_use,
            "description": blurb,
            **frozen,
            "held_out": _read_once(test, values, cut, direction),
            "held_out_hard_negatives_only": _read_once(
                _hard_negative_view(test), values, cut, direction),
        })

    # The shipped scorer is reported at ITS OWN frozen threshold -- select_
    # threshold()'s 0.01 grid, the value in out/threshold.json -- and is not
    # re-swept over observed values like the four challengers above.
    #
    # Two reasons, and the second is the important one. The table's headline row
    # has to be the number the system actually ships, or the Benchmark tab shows
    # two different held-out F1s for one detector. And a sweep over observed
    # values is strictly finer than a 0.01 grid, so granting it to the
    # challengers while holding the incumbent to its shipped freeze errs against
    # the incumbent -- the safe direction for a check whose whole job is to catch
    # this system flattering itself. On this data it costs the shipped row
    # 0.8421 -> 0.8000, and the conclusion does not depend on it either way.
    shipped_threshold, shipped_meta = select_threshold(cfg, validation)
    scores = {c.component_id: c.score for c in cands}
    rows.append({
        "baseline": "ring_score",
        "uses_graph": "fully",
        "description": "The shipped weighted score over all seven signals, at "
                       "the threshold frozen in out/threshold.json.",
        "cutoff": shipped_threshold,
        "direction": ">=",
        "validation_f1": shipped_meta["validation_f1_at_threshold"],
        "validation_components": len(validation),
        "cutoff_protocol": "select_threshold() 0.01 grid, as shipped -- not the "
                           "finer value sweep the four challengers get",
        "held_out": _read_once(test, scores, shipped_threshold, ">="),
        "held_out_hard_negatives_only": _read_once(
            _hard_negative_view(test), scores, shipped_threshold, ">="),
    })

    return {
        "measurement": "prd-row-63-baseline-sanity-checks",
        "protocol": (
            "Each baseline sweeps its own cutoff and direction on validation "
            "rows only, freezes both, then reads the held-out split once. "
            "Directions are swept because RISK-001 showed a one-directional "
            "sweep reports an inverted signal as useless."
        ),
        "transaction_level_amount_cutoff": amount_cutoff,
        "transaction_level_amount_cutoff_fitted_on": "train+validation",
        "transaction_level_age_cut_days": TXN_LEVEL_YOUNG_ACCOUNT_DAYS,
        "transaction_level_age_cut_sensitivity_validation_f1": age_cut_sensitivity(
            txns, graph, design_ids, validation),
        "baselines": rows,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }


# --------------------------------------------------------------------------
# row 70 -- leave-one-group-out ablation
# --------------------------------------------------------------------------


def _one_configuration(cfg: Config, name: str, removed: tuple[str, ...],
                       labels: list[Label]) -> dict:
    """Rescore with a group zeroed, freeze on validation, read test once.

    Weights are RENORMALISED after zeroing, for the reason recorded with the
    temporal ablation: holding the survivors fixed and letting the total fall
    below 1.0 multiplies every score by a constant, which measured against a
    fixed threshold is a change of units rather than an ablation.

    `select_threshold()` itself is used -- the audited function, not a private
    copy -- so "same protocol as the shipped model" is literally true. The
    ablated scorers are weighted sums on the same [0, 1] scale and in the same
    orientation, so nothing about them needs the baselines' value sweep.
    """
    weights = _renormalised({
        s: cfg.weights[s] for s in SIGNALS
        if cfg.weights[s] > 0 and s not in removed
    })
    cands = rescore(cfg, weights)
    validation = [c for c in cands if c.split == "validation"]
    test = [c for c in cands if c.split == "test"]

    threshold, meta = select_threshold(cfg, validation)
    held = score_at(test, threshold)
    hard = score_at(_hard_negative_view(test), threshold)

    return {
        "group": name,
        "signals_removed": list(removed),
        "weight_removed": round(sum(cfg.weights[s] for s in removed), 4),
        "weights": {s: round(w, 4) for s, w in weights.items()},
        "threshold": threshold,
        "threshold_selected_on": "validation",
        "validation_f1": meta["validation_f1_at_threshold"],
        "held_out": {**held, **ring_recovery(cfg, test, labels, threshold)},
        "held_out_hard_negatives_only": hard,
    }


def ablation_report(cfg: Config, labels: list[Label]) -> dict:
    """Full model against each feature group removed, one at a time.

    The full row goes through the same `rescore` path as the ablated ones rather
    than reusing the pipeline's candidates, so a difference between rows can only
    come from the weights.
    """
    rows = [_one_configuration(cfg, "full", (), labels)]
    for group, removed in ABLATION_GROUPS.items():
        rows.append(_one_configuration(cfg, group, removed, labels))

    full = rows[0]["held_out"]
    for row in rows[1:]:
        row["delta_f1"] = round(row["held_out"]["f1"] - full["f1"], 4)
        row["delta_hard_negative_f1"] = round(
            row["held_out_hard_negatives_only"]["f1"]
            - rows[0]["held_out_hard_negatives_only"]["f1"], 4)
        row["identical_to_full"] = (
            row["weights"] == rows[0]["weights"]
            and row["held_out"] == full
        )

    return {
        "measurement": "prd-row-70-leave-one-group-out-ablation",
        "protocol": (
            "Each configuration zeroes one feature group, renormalises the "
            "survivors, selects its own threshold on validation rows only via "
            "select_threshold(), then reads the held-out split once. Six "
            "configurations, six independent freezes."
        ),
        "grouping": {g: list(s) for g, s in ABLATION_GROUPS.items()},
        "grouping_note": (
            "A partition of the seven signals: structural (what accounts share) "
            "against behavioural (how accounts act). Asserted at import."
        ),
        "configurations": rows,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }
