"""Expected-loss weight selection, with the non-triviality panel as a hard gate.

Nothing in this module has been run against a candidate. It is the frozen
protocol described in `weight_search_protocol.md`, written before the search so
the rules cannot be adjusted once the numbers are visible.

The gate is the point of this module. bugs.md L2 records that held-out F1 rose
from 0.8000 to 0.8889 twice, by two unrelated mechanisms, and that the
non-triviality panel went PASS -> FAIL both times. A metric computed on this
benchmark improves when the model gets better AND when the benchmark gets
easier, and it does not distinguish them. An optimiser will find the second kind
of solution preferentially, because it is cheaper.

So a weight vector that fails the panel is not a worse candidate. It is not a
candidate. `gated_expected_loss()` raises `PanelGateFailure` instead of
returning a number, in the same way `held_out_view()` raises `TestSetLeak`
instead of returning test rows: the protocol is enforced by what the function
can do, not by remembering to check afterwards.

Two further guarantees, both structural rather than remembered:

* `select_weights()` takes validation candidates and asserts it received nothing
  else, exactly as `select_threshold()` does.
* `evaluate_frozen_policy()` refuses to touch the test split until the winning
  policy has been written to disk.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .config import SIGNALS, Config
from .evaluate import Candidate, build_candidates, score_at
from .generate import generate
from .graph import build_graph
from .integrity import non_triviality_panel
from .score import score_all
from .split import assign_splits

DESIGN_SPLIT = "validation"


class PanelGateFailure(AssertionError):
    """Raised when a weight vector that fails the non-triviality panel is scored.

    Not an error to be caught and worked around. It means the candidate made the
    benchmark easier, which is the failure mode this whole module exists to
    prevent.
    """


class PolicyNotFrozen(AssertionError):
    """Raised when the held-out split is read before a policy is on disk."""


# --------------------------------------------------------------------------
# cost inputs -- derived, never round numbers (PRD "Cost Inputs")
# --------------------------------------------------------------------------

# Analyst effort assumption, documented rather than derived: a coordinated-abuse
# case touching a handful of accounts takes an analyst about 20 minutes at a
# fully-loaded cost of INR 1500/hour. This is the one input the dataset cannot
# supply and it is flagged as an assumption everywhere it is used.
ANALYST_MINUTES_PER_COMPONENT = 20
ANALYST_COST_PER_HOUR = 1500.0

# Fraction of a wrongly-escalated legitimate component's exposure that the
# business actually loses -- friction, goodwill, abandoned volume -- rather than
# the whole of it. A blocked legitimate customer does not cost their lifetime
# volume; they cost the margin on the disrupted portion plus the risk of churn.
FP_FRICTION_RATE = 0.02

# Fraction of a missed ring's exposure the platform absorbs. 1.00 says an
# undetected ring's transactions settle and the chargebacks land on the
# platform. Deliberately the pessimistic end; the sensitivity table must show
# what happens at lower values.
FN_ABSORBED_FRACTION = 1.00


def derive_costs(design: list[Candidate]) -> dict[str, Any]:
    """Cost inputs traceable to the dataset's own exposure figures.

    Computed on design-split candidates only. Medians, not means: component
    exposure is long-tailed and a mean would let one large ring set the price of
    every decision.
    """
    pos = [c.exposure for c in design if c.is_positive]
    neg = [c.exposure for c in design if not c.is_positive]
    if not pos or not neg:
        raise ValueError("cost derivation needs both classes in the design split")

    review = ANALYST_COST_PER_HOUR * ANALYST_MINUTES_PER_COMPONENT / 60.0
    median_ring = statistics.median(pos)
    median_neg = statistics.median(neg)
    fn = median_ring * FN_ABSORBED_FRACTION
    fp = review + median_neg * FP_FRICTION_RATE
    return {
        "manual_review": round(review, 2),
        "false_negative": round(fn, 2),
        "false_positive": round(fp, 2),
        "derivation": {
            "manual_review": (
                f"{ANALYST_MINUTES_PER_COMPONENT} analyst-minutes per component at "
                f"INR {ANALYST_COST_PER_HOUR:.0f}/hour fully loaded. ASSUMPTION -- "
                "the dataset carries no analyst-effort figure."
            ),
            "false_negative": (
                f"median ring-component exposure INR {median_ring:,.2f} on "
                f"train+validation, times FN_ABSORBED_FRACTION "
                f"{FN_ABSORBED_FRACTION:.2f}"
            ),
            "false_positive": (
                f"one manual review (INR {review:,.2f}) plus "
                f"FP_FRICTION_RATE {FP_FRICTION_RATE:.2f} of median "
                f"negative-component exposure INR {median_neg:,.2f}"
            ),
            "ratio_fn_to_fp": round(fn / fp, 1),
        },
        "inputs_from_data": {
            "median_ring_exposure": round(median_ring, 2),
            "median_negative_exposure": round(median_neg, 2),
            "n_positive": len(pos),
            "n_negative": len(neg),
        },
    }


def expected_loss(cands: list[Candidate], threshold: float,
                  costs: dict[str, Any]) -> dict[str, float]:
    """Expected loss at one threshold. Flagged components are reviewed."""
    c = score_at(cands, threshold)
    tp, fp, fn = int(c["tp"]), int(c["fp"]), int(c["fn"])
    review = (tp + fp) * costs["manual_review"]
    loss = fn * costs["false_negative"] + fp * costs["false_positive"] + review
    return {
        "expected_loss": round(loss, 2),
        "loss_per_component": round(loss / max(1, len(cands)), 2),
        "review_cost": round(review, 2),
        "review_rate": round((tp + fp) / max(1, len(cands)), 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": int(c["tn"]),
    }


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

def panel_verdict(cfg: Config, design: list[Candidate]) -> dict[str, Any]:
    panel = non_triviality_panel(cfg, design)
    return {
        "verdict": panel["verdict"],
        "positives_below_max_negative":
            panel["positives_below_max_negative"]["fraction"],
        "hard_negatives_inside_positive_range":
            panel["hard_negatives_inside_positive_range"],
        "shared_device_only_baseline_f1": panel["shared_device_only_baseline_f1"],
        "failing_checks": [
            name for name, row in panel["checks"].items()
            if row["status"] == "FAIL"
        ],
    }


def gated_expected_loss(cfg: Config, design: list[Candidate],
                        threshold: float, costs: dict[str, Any]) -> dict[str, float]:
    """Expected loss, but only for a candidate the panel accepts.

    A candidate that fails the panel cannot be scored at all. It does not get a
    number that is later discarded -- there is no number. See bugs.md L2.
    """
    v = panel_verdict(cfg, design)
    if v["verdict"] != "PASS":
        raise PanelGateFailure(
            f"non-triviality panel returned {v['verdict']} "
            f"(failing: {v['failing_checks']}, positives below max negative "
            f"{v['positives_below_max_negative']}). This weight vector makes the "
            "benchmark easier rather than the scorer better, so it has no "
            "expected loss to report. bugs.md L2."
        )
    return expected_loss(design, threshold, costs)


# --------------------------------------------------------------------------
# candidates -- a fixed list, declared in advance, with no search space
# --------------------------------------------------------------------------

def _renormalised(active: dict[str, float]) -> dict[str, float]:
    total = sum(active.values())
    if total <= 0:
        raise ValueError("weight policy has no positive weight")
    out = {name: 0.0 for name in SIGNALS}
    out.update({k: v / total for k, v in active.items()})
    return out


def policy_a_baseline(cfg: Config, design: list[Candidate]) -> dict[str, float]:
    """Control. The current hand-set Tier 0 weights, unchanged."""
    return dict(cfg.weights)


def policy_b_equal(cfg: Config, design: list[Candidate]) -> dict[str, float]:
    """Equal weight on every signal not already zeroed by a filed RISK item.

    Tests whether the hand-tuned ratios bought anything at all.
    """
    return _renormalised({s: 1.0 for s in SIGNALS if cfg.weights[s] > 0})


def policy_c_separation(cfg: Config, design: list[Candidate]) -> dict[str, float]:
    """Weight proportional to each signal's ring-minus-family separation.

    Uses the diagnostic that drove every RISK fix in this build. Signals with a
    non-positive delta get zero.
    """
    pos = [c for c in design if c.is_positive]
    fam = [c for c in design if not c.is_positive and c.has_family]
    active: dict[str, float] = {}
    for s in SIGNALS:
        d = (statistics.fmean([c.signals[s] for c in pos])
             - statistics.fmean([c.signals[s] for c in fam]))
        if d > 0:
            active[s] = d
    return _renormalised(active)


def policy_d_drop_flagged(cfg: Config, design: list[Candidate]) -> dict[str, float]:
    """Zero both signals with a filed defect: instrument_sharing and
    merchant_concentration (RISK-004, RISK-002).

    Expected to be REFUSED by the gate. Zeroing `instrument_sharing` alone
    already took positives-below-max-negative to 0.1250 against a 0.20 bound.
    Included deliberately: a protocol whose gate never fires has not been shown
    to work.
    """
    return _renormalised({
        s: cfg.weights[s] for s in SIGNALS
        if cfg.weights[s] > 0 and s not in ("instrument_sharing",
                                            "merchant_concentration")
    })


def policy_e_drop_temporal(cfg: Config, design: list[Candidate]) -> dict[str, float]:
    """Zero `temporal_burst`, the signal the ablation found redundant (D1)."""
    return _renormalised({
        s: cfg.weights[s] for s in SIGNALS
        if cfg.weights[s] > 0 and s != "temporal_burst"
    })


CANDIDATES: dict[str, Callable[[Config, list[Candidate]], dict[str, float]]] = {
    "A_baseline": policy_a_baseline,
    "B_equal": policy_b_equal,
    "C_separation_proportional": policy_c_separation,
    "D_drop_flagged": policy_d_drop_flagged,
    "E_drop_temporal": policy_e_drop_temporal,
}


# --------------------------------------------------------------------------
# protocol
# --------------------------------------------------------------------------

def rescore(cfg: Config, weights: dict[str, float]) -> list[Candidate]:
    """Rebuild candidates under a weight vector. The generator is not touched."""
    cfg2 = replace(cfg, weights=weights)
    txns, labels = generate(cfg2)
    graph = build_graph(cfg2, txns)
    scores = score_all(cfg2, txns, graph)
    splits = assign_splits(cfg2, graph, labels)
    return build_candidates(cfg2, graph, scores, splits, labels)


def select_weights(cfg: Config, validation: list[Candidate],
                   costs: dict[str, Any]) -> dict[str, Any]:
    """Score every candidate on VALIDATION only, gated by the panel.

    Takes validation candidates as its whole input, exactly as
    `select_threshold()` does. There is no parameter through which test data
    could reach it.
    """
    assert all(c.split == DESIGN_SPLIT for c in validation), (
        "select_weights received non-validation candidates -- "
        "this would be weight fitting on held-out data"
    )
    raise NotImplementedError(
        "Not run. The protocol is frozen in weight_search_protocol.md and "
        "awaiting confirmation before any candidate is scored."
    )


def evaluate_frozen_policy(candidates: list[Candidate],
                           policy_path: Path) -> list[Candidate]:
    """Test rows -- available only once the winning policy is on disk."""
    if not policy_path.exists():
        raise PolicyNotFrozen(
            f"{policy_path.name} has not been frozen. The selected weight vector, "
            "its validation expected loss and its panel verdict must be recorded "
            "before the test split is read, or the comparison is not held out."
        )
    return [c for c in candidates if c.split == "test"]


def freeze_policy(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
