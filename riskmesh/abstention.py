"""Abstention / review-band policy, layered on the frozen A_baseline scorer.

Protocol: `abstention_protocol.md`, frozen before this module was pointed at
selection. Frozen record: `out/abstention_policy.json`.

This module does not touch the scorer or the binary threshold (0.23) that
`weight_search_protocol.md` already froze. Those numbers -- F1 0.8000, expected
loss 9,392.92 -- stay exactly as reported. What this module adds is a second,
independent decision layer: given the same scores, split the flagged region
into a Review band (deferred to a human, no automatic action) and an Escalate
region (same handling the binary policy already gave everything above 0.23),
plus an Allow region below the review band.

    score < t_lo           -> Allow      (no review, no action)
    t_lo <= score < t_hi    -> Review     (one manual review; fp/fn cost waived)
    score >= t_hi           -> Escalate   (same accounting as the binary "flag")

At t_lo == t_hi this collapses exactly onto the existing binary
`costmodel.expected_loss()` -- there is no Review band, Allow is the old
negative-predicted set and Escalate is the old positive-predicted set. That
collapse is a permanent test (`tests/test_riskmesh.py`), not just a design-doc
claim, because a future edit to either formula that breaks the equivalence
would silently make the two cost models inconsistent with each other.

Same discipline as `costmodel.py` throughout: `select_abstention_band()` takes
design candidates and asserts it received nothing else, the review-rate gate is
declared here (before any band has been scored) rather than fitted after
seeing a result, and `evaluate_frozen_abstention_policy()` cannot reach a test
row without a frozen policy already on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Config
from .costmodel import DESIGN_SPLIT, DESIGN_SPLITS, PanelGateFailure, panel_verdict
from .evaluate import Candidate

GRID = [i / 100.0 for i in range(101)]

# Pre-declared, on DESIGN (train+validation) coverage -- not validation alone,
# for the same reason the two difficulty gates in costmodel.py are evaluated on
# design: more data, less small-sample noise in the coverage measurement, and
# the failure mode being guarded against (an optimiser dumping cost onto a
# cheap escape hatch, bugs.md L2) is the same one those gates exist for.
#
# 0.25 is a business-policy choice, not a data fact -- there is nothing in this
# benchmark that derives it. It is set well above the unconstrained optimum
# found while designing this module (6.45% on validation, 10.14% on design) so
# it does not bind today; it exists as a structural backstop against a
# different result on a future run, not because today's numbers demanded it.
MAX_REVIEW_RATE = 0.25

# Phase-1 cost-model assumption, not an empirical measurement (see
# abstention_protocol.md): a component routed to Review is resolved correctly
# by the analyst before any automated action is taken, so it costs exactly one
# manual review and neither a false-positive nor a false-negative cost. This is
# the entire mechanism by which a review band can reduce expected loss, and it
# is not derivable from the dataset any more than ANALYST_MINUTES_PER_COMPONENT
# in costmodel.py was. A partial-credit version (an analyst error rate) is
# future work, not implemented here.


class ReviewBandGateFailure(AssertionError):
    """Raised when no (t_lo, t_hi) keeps design review coverage under the cap.

    Mirrors costmodel.PanelGateFailure / DifficultyGateFailure: a band that
    fails this gate is not a worse candidate, it is not a candidate. No
    expected-loss figure is produced for it.
    """


class AbstentionPolicyNotFrozen(AssertionError):
    """Raised when the held-out split is read before a band is on disk.

    Mirrors costmodel.PolicyNotFrozen exactly.
    """


def three_way_stats(cands: list[Candidate], t_lo: float, t_hi: float,
                    costs: dict[str, Any]) -> dict[str, Any]:
    """Expected loss and coverage breakdown for one (t_lo, t_hi) band.

    At t_lo == t_hi, Review is empty and this is bit-for-bit the binary
    costmodel.expected_loss() formula: Allow-positive costs C_fn, Escalate-
    negative costs C_fp + C_review, Escalate-positive costs C_review. See the
    permanent collapse test in tests/test_riskmesh.py.
    """
    c_fn, c_fp, c_review = (costs["false_negative"], costs["false_positive"],
                            costs["manual_review"])
    loss = 0.0
    n = len(cands)
    allow = allow_missed_positives = 0
    review = review_positives = review_negatives = review_family = 0
    escalate = escalate_tp = escalate_fp = 0
    for c in cands:
        if c.score < t_lo:
            allow += 1
            if c.is_positive:
                loss += c_fn
                allow_missed_positives += 1
        elif c.score < t_hi:
            review += 1
            loss += c_review
            if c.is_positive:
                review_positives += 1
            else:
                review_negatives += 1
                if c.has_family:
                    review_family += 1
        else:
            escalate += 1
            loss += c_review
            if c.is_positive:
                escalate_tp += 1
            else:
                loss += c_fp
                escalate_fp += 1
    return {
        "t_lo": round(t_lo, 2), "t_hi": round(t_hi, 2),
        "n": n,
        "expected_loss": round(loss, 2),
        "loss_per_component": round(loss / max(1, n), 4),
        "allow": allow, "allow_missed_positives": allow_missed_positives,
        "review": review, "review_rate": round(review / max(1, n), 4),
        "review_positives": review_positives,
        "review_negatives": review_negatives,
        "review_family": review_family,
        "escalate": escalate, "escalate_tp": escalate_tp,
        "escalate_fp": escalate_fp,
    }


def select_abstention_band(cfg: Config, design: list[Candidate],
                           costs: dict[str, Any]) -> dict[str, Any]:
    """Select (t_lo, t_hi) on validation, gated by review coverage on design.

    Objective hierarchy, in order (abstention_protocol.md):
      1. structurally no test row can reach this function (design assertion)
      2. panel PASS (checked once -- it does not vary with the band; the
         scorer and weights are unchanged from the already-gated A_baseline)
      3. review-rate feasibility gate, per candidate band, on design coverage
      4. minimise expected loss, per candidate band, on validation only
    Freezing and the held-out read are separate steps, outside this function.
    """
    assert all(c.split in DESIGN_SPLITS for c in design), (
        "select_abstention_band received non-design candidates -- "
        "this would be band selection on held-out data"
    )
    v = panel_verdict(cfg, design)
    if v["verdict"] != "PASS":
        raise PanelGateFailure(
            f"non-triviality panel returned {v['verdict']} on the design split "
            "backing this abstention search. The scorer is supposed to be the "
            "already-gated A_baseline -- if the panel fails here, something "
            "upstream changed the scorer or the data, not just the band."
        )
    validation = [c for c in design if c.split == DESIGN_SPLIT]

    best: dict[str, Any] | None = None
    bands_considered = 0
    bands_refused_by_coverage = 0
    for t_lo in GRID:
        for t_hi in GRID:
            if t_hi < t_lo:
                continue
            design_stats = three_way_stats(design, t_lo, t_hi, costs)
            if design_stats["review_rate"] > MAX_REVIEW_RATE:
                bands_refused_by_coverage += 1
                continue
            bands_considered += 1
            val_stats = three_way_stats(validation, t_lo, t_hi, costs)
            if best is None or val_stats["expected_loss"] < best["expected_loss"]:
                best = {
                    **val_stats,
                    "design_review_rate": design_stats["review_rate"],
                    "design_review_positives": design_stats["review_positives"],
                    "design_review_negatives": design_stats["review_negatives"],
                    "design_review_family": design_stats["review_family"],
                }

    if best is None:
        raise ReviewBandGateFailure(
            f"no (t_lo, t_hi) keeps design review_rate <= {MAX_REVIEW_RATE}. "
            "Every band tried covers more of the design split than the "
            "pre-declared cap allows -- this would be reviewing most of the "
            "dataset, not operating a policy."
        )

    return {
        "max_review_rate_gate": MAX_REVIEW_RATE,
        "bands_considered": bands_considered,
        "bands_refused_by_coverage": bands_refused_by_coverage,
        "panel_verdict": v["verdict"],
        "selected_on": "validation (expected-loss sweep); "
                       "review-rate gate on train+validation",
        **best,
    }


def freeze_abstention_policy(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def evaluate_frozen_abstention_policy(candidates: list[Candidate],
                                      policy_path: Path) -> list[Candidate]:
    """Test rows -- available only once the selected band is on disk."""
    if not policy_path.exists():
        raise AbstentionPolicyNotFrozen(
            f"{policy_path.name} has not been frozen. t_lo, t_hi and the "
            "design review-rate must be recorded before the test split is "
            "read, or the comparison is not held out."
        )
    return [c for c in candidates if c.split == "test"]
