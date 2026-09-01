"""Expected-loss weight selection, with the non-triviality panel as a hard gate.

The protocol is described in `weight_search_protocol.md`. In `96ae30f`
("Freeze the weight-search protocol before running any candidate"),
`select_weights()` was a stub that raised
`NotImplementedError("Not run. The protocol is frozen in
weight_search_protocol.md and awaiting confirmation before any candidate is
scored.")` -- the search was structurally prevented from running before the
freeze was confirmed, and that stub is the evidence it worked. The panel gate
was already present in that commit; the two difficulty gates below --
`MIN_HARD_NEGATIVES_IN_RANGE` and `MIN_POSITIVES_BELOW_MAX_NEGATIVE` -- were
not. Both difficulty gates and `select_weights()`'s real body arrived together
in `9cafa71` ("Tighten the weight gate, run the search"), the same commit that
ran the search over the five declared candidates, so no ordering between the
gates and the implementation is provable from history in either direction. The
gates tightened the bar rather than relaxed it, and every candidate was
evaluated under them; there is no evidence they were fitted to results. But an
earlier version of this docstring claimed the gates preceded the
implementation, and that specific claim is not supported by the history --
this paragraph replaces it.

The gate is the point of this module. bugs.md L2 records that held-out F1 rose
from 0.8000 to 0.8889 twice, by two unrelated mechanisms, and that the
non-triviality panel went PASS -> FAIL both times. A metric computed on this
benchmark improves when the model gets better AND when the benchmark gets
easier, and it does not distinguish them. An optimiser will find the second kind
of solution preferentially, because it is cheaper.

So a weight vector that fails any gate is not a worse candidate. It is not a
candidate. `gated_expected_loss()` raises `PanelGateFailure` or
`DifficultyGateFailure` instead of returning a number, in the same way
`held_out_view()` raises `TestSetLeak` instead of returning test rows: the
protocol is enforced by what the function can do, not by remembering to check
afterwards. Panel PASS is necessary and not sufficient -- two absolute
difficulty bounds sit on top of it.

Two further guarantees, both structural rather than remembered:

* `select_weights()` takes design candidates and raises if it received anything
  else, the same discipline `select_threshold()` enforces; the threshold sweep
  inside it uses validation rows only.
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
DESIGN_SPLITS = ("train", "validation")


class PanelGateFailure(AssertionError):
    """Raised when a weight vector that fails the non-triviality panel is scored.

    Not an error to be caught and worked around. It means the candidate made the
    benchmark easier, which is the failure mode this whole module exists to
    prevent.
    """


class DifficultyGateFailure(PanelGateFailure):
    """Raised when a candidate passes the panel but erodes the benchmark anyway.

    The panel's own bounds are the Tier 0 minimums for a dataset to be worth
    evaluating on at all (`positives_below_max_negative >= 0.20`,
    `hard_negative_in_positive_range >= 1`). They are necessary and, as the gate
    demonstration showed, not sufficient: policy B cleared the panel while taking
    positives-below-max-negative from 0.5625 to 0.3125 and hard negatives in the
    positive range from 4 to 1 -- most of the benchmark's difficulty, spent
    without the panel objecting.

    Subclasses PanelGateFailure so anything catching the gate catches both.
    """


class PolicyNotFrozen(AssertionError):
    """Raised when the held-out split is read before a policy is on disk."""


class DesignSplitViolation(AssertionError):
    """Raised when a design-only selection function receives a test row.

    Subclasses AssertionError so it is still caught by callers (and tests) that
    check for the bare assert this replaced; the guard now also fires under
    `python -O`, which strips `assert` statements.
    """


# --------------------------------------------------------------------------
# feasibility constraints
# --------------------------------------------------------------------------

# Two absolute bounds, on top of the panel verdict. Absolute rather than a
# relative margin from the incumbent on purpose: a margin from A would move
# whenever A moved, so a future weight change could ratchet the benchmark's
# difficulty down one accepted step at a time with every individual step looking
# reasonable. These numbers do not move with the incumbent.
#
# DECLARED BEFORE ANY CANDIDATE WAS SELECTED, and for a specific measured reason
# rather than as a tidy default -- see bugs.md L2. Held-out F1 rose from 0.8000
# to 0.8889 twice, by two unrelated mechanisms, and the non-triviality panel went
# PASS -> FAIL both times. A higher score on this benchmark can mean a better
# scorer or an easier benchmark, and the metric cannot tell them apart. So the
# difficulty is constrained separately, before expected loss is allowed to
# matter, instead of being reported next to it afterwards.
MIN_HARD_NEGATIVES_IN_RANGE = 4
MIN_POSITIVES_BELOW_MAX_NEGATIVE = 0.45


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


def derive_costs(design: list[Candidate],
                 fn_absorbed_fraction: float = FN_ABSORBED_FRACTION,
                 fp_friction_rate: float = FP_FRICTION_RATE) -> dict[str, Any]:
    """Cost inputs traceable to the dataset's own exposure figures.

    Computed on design-split candidates only. Medians, not means: component
    exposure is long-tailed and a mean would let one large ring set the price of
    every decision.

    `fn_absorbed_fraction` / `fp_friction_rate` default to this module's own
    declared constants -- the protocol's actual, frozen cost model. They are
    parameters (not a change to that model) so a sensitivity sweep can call
    this same function once per grid cell instead of re-deriving the
    arithmetic elsewhere; see `riskmesh/freeze.py::_weight_sensitivity()`,
    which is the only caller that overrides them.
    """
    pos = [c.exposure for c in design if c.is_positive]
    neg = [c.exposure for c in design if not c.is_positive]
    if not pos or not neg:
        raise ValueError("cost derivation needs both classes in the design split")

    review = ANALYST_COST_PER_HOUR * ANALYST_MINUTES_PER_COMPONENT / 60.0
    median_ring = statistics.median(pos)
    median_neg = statistics.median(neg)
    fn = median_ring * fn_absorbed_fraction
    fp = median_neg * fp_friction_rate
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
                f"{fn_absorbed_fraction:.2f}"
            ),
            "false_positive": (
                f"FP_FRICTION_RATE {fp_friction_rate:.2f} of median "
                f"negative-component exposure INR {median_neg:,.2f} -- no "
                "separate review cost: the generic (tp+fp)*C_review term "
                "already prices one review per flagged component (see "
                "deferred_decisions.md D3, resolved Phase 10)"
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
                        threshold: float, costs: dict[str, Any],
                        score_on: list[Candidate] | None = None) -> dict[str, float]:
    """Expected loss, but only for a candidate that clears all three gates.

    Panel PASS is necessary and not sufficient. A candidate that fails any gate
    cannot be scored at all: it does not get a number that is later discarded --
    there is no number. See bugs.md L2.

    `design` is what the gates are evaluated on (train+validation, so the
    difficulty measurement uses all 16 design positives). `score_on` is what the
    loss is computed on, and defaults to `design`; the selection passes the
    validation rows there, because a threshold must be chosen on validation
    alone. Both arguments are design-split views -- neither can carry test rows.
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
    if v["hard_negatives_inside_positive_range"] < MIN_HARD_NEGATIVES_IN_RANGE:
        raise DifficultyGateFailure(
            f"hard negatives inside the positive range "
            f"{v['hard_negatives_inside_positive_range']} < "
            f"{MIN_HARD_NEGATIVES_IN_RANGE}. The panel passed, but the hard "
            "negatives are the benchmark; a candidate that pushes them out of "
            "the positive range has made the task easier. bugs.md L2."
        )
    if v["positives_below_max_negative"] < MIN_POSITIVES_BELOW_MAX_NEGATIVE:
        raise DifficultyGateFailure(
            f"positives below the top negative "
            f"{v['positives_below_max_negative']:.4f} < "
            f"{MIN_POSITIVES_BELOW_MAX_NEGATIVE}. The panel passed, but the "
            "classes have pulled apart far enough that the benchmark is no "
            "longer measuring what it was built to measure. bugs.md L2."
        )
    return expected_loss(design if score_on is None else score_on,
                         threshold, costs)


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
    """Weight proportional to each signal's ring-minus-hard-negative-cluster
    separation (Task 4: `has_family` covers office/hostel/retail alongside
    family now, not family alone -- "family" here is a holdover name for
    what the comparison group actually is; the computation is unchanged).

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


def _design_only(cands: list[Candidate]) -> list[Candidate]:
    """Train+validation rows. Raises if a test row would slip through."""
    view = [c for c in cands if c.split in DESIGN_SPLITS]
    if any(c.split == "test" for c in view):  # pragma: no cover - belt and braces
        raise AssertionError("design view contains test rows")
    return view


def select_weights(cfg: Config, design: list[Candidate],
                   costs: dict[str, Any]) -> dict[str, Any]:
    """Score every candidate on train+validation only, behind all three gates.

    Takes design candidates as its whole input and asserts it received nothing
    else, in the same shape as `select_threshold()`. Gates are evaluated on
    train+validation; the threshold sweep uses validation rows only. No path
    through this function reaches the test split.

    Feasibility is checked before expected loss, not alongside it: an infeasible
    candidate never receives a number to be compared against.
    """
    if not all(c.split in DESIGN_SPLITS for c in design):
        raise DesignSplitViolation(
            "select_weights received non-design candidates -- "
            "this would be weight fitting on held-out data"
        )

    results: list[dict[str, Any]] = []
    for name, policy in CANDIDATES.items():
        weights = policy(cfg, design)
        rescored = _design_only(rescore(cfg, weights))
        validation = [c for c in rescored if c.split == DESIGN_SPLIT]
        v = panel_verdict(cfg, rescored)
        row: dict[str, Any] = {
            "policy": name,
            "weights": {k: round(x, 4) for k, x in weights.items()},
            "panel_verdict": v["verdict"],
            "panel_failing_checks": v["failing_checks"],
            "positives_below_max_negative": v["positives_below_max_negative"],
            "hard_negatives_inside_positive_range":
                v["hard_negatives_inside_positive_range"],
        }
        best: dict[str, Any] | None = None
        try:
            for i in range(101):
                t = i / 100.0
                loss = gated_expected_loss(cfg, rescored, t, costs,
                                           score_on=validation)
                if best is None or loss["expected_loss"] < best["expected_loss"]:
                    best = {**loss, "threshold": t}
        except PanelGateFailure as exc:
            row["feasible"] = False
            row["refused_by"] = type(exc).__name__
            row["reason"] = str(exc)
        else:
            assert best is not None
            row["feasible"] = True
            row.update(best)
        results.append(row)

    feasible = [r for r in results if r["feasible"]]
    winner = min(
        feasible,
        key=lambda r: (r["expected_loss"],
                       -r["positives_below_max_negative"],
                       r["policy"] != "A_baseline"),
    ) if feasible else None

    return {
        "protocol": "weight_search_protocol.md",
        "gates": {
            "panel_verdict": "PASS",
            "hard_negatives_inside_positive_range":
                f">= {MIN_HARD_NEGATIVES_IN_RANGE}",
            "positives_below_max_negative":
                f">= {MIN_POSITIVES_BELOW_MAX_NEGATIVE}",
            "declared": (
                "Commit 96ae30f froze the protocol with select_weights() as a "
                "stub raising NotImplementedError -- the search was "
                "structurally prevented from running before the freeze was "
                "confirmed. The panel gate was already present there; the two "
                "difficulty gates were not. Both difficulty gates and "
                "select_weights()'s real body arrived together in commit "
                "9cafa71, the same commit that ran the search over the five "
                "declared candidates, so no ordering between the gates and the "
                "implementation is provable from history. They tightened the "
                "bar rather than relaxed it, and every candidate was evaluated "
                "under them; there is no evidence they were fitted to results. "
                "The reason is bugs.md L2: held-out F1 rose 0.8000 -> 0.8889 "
                "twice, by unrelated mechanisms, while the non-triviality "
                "panel went PASS -> FAIL both times. A higher score on this "
                "benchmark can mean a better scorer or an easier benchmark and "
                "the metric cannot distinguish them, so difficulty is "
                "constrained structurally rather than reported after the fact."
            ),
            "enforcement": (
                "gated_expected_loss() raises PanelGateFailure or "
                "DifficultyGateFailure instead of returning a number. An "
                "infeasible candidate has no expected loss at all."
            ),
        },
        "costs": costs,
        "selected_on": "validation (threshold sweep); gates on train+validation",
        "candidates": results,
        "feasible": [r["policy"] for r in feasible],
        "infeasible": [r["policy"] for r in results if not r["feasible"]],
        "winner": winner["policy"] if winner else None,
        "winner_threshold": winner["threshold"] if winner else None,
        "winner_expected_loss": winner["expected_loss"] if winner else None,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
    }


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
