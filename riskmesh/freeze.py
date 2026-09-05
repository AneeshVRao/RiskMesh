"""Regenerate the four frozen protocol records:

    python -m riskmesh.freeze weights
    python -m riskmesh.freeze abstention
    python -m riskmesh.freeze xgboost
    python -m riskmesh.freeze graphsage
    python -m riskmesh.freeze all

Before this module existed, `select_weights()`, `select_abstention_band()`,
`select_xgboost_model()`, `select_gnn_model()` and all four `freeze_*()`
functions had zero callers anywhere in the repo -- `experiments/*.json` were
committed files with no code path that regenerated them. This module is that
path. It does not reimplement any selection logic: every stage below is
`build candidates -> call the existing select_*() on a design-only view ->
call the existing freeze_*() -> take the single held-out read (if the
protocol permits one) -> record it in the same JSON`.

`weights` and `abstention` stay stdlib-only (G7): xgboost/torch (and the
modules that import them at module scope) are imported inside the `xgboost`
and `graphsage` functions only, never at this module's top level.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import Config
from .costmodel import (
    CANDIDATES as WEIGHT_CANDIDATES,
    DESIGN_SPLITS,
    derive_costs,
    evaluate_frozen_policy,
    expected_loss,
    freeze_policy,
    panel_verdict,
    rescore,
    select_weights,
)
from .evaluate import Candidate, build_candidates, evaluate
from .generate import Label, generate
from .graph import Graph, build_graph
from .score import score_all
from .split import assign_splits

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "experiments"

WEIGHT_POLICY = EXPERIMENTS / "weight_policy.json"
ABSTENTION_POLICY = EXPERIMENTS / "abstention_policy.json"
XGBOOST_POLICY = EXPERIMENTS / "xgboost_policy.json"
GRAPHSAGE_POLICY = EXPERIMENTS / "graphsage_policy.json"


def _build(cfg: Config) -> tuple[Graph, list[Candidate], list[Label]]:
    """One fresh generate -> graph -> score -> split -> candidates pass.
    Mirrors `tests/test_ml.py::build()` / `tests/test_gnn.py::build()` /
    `riskmesh/__main__.py::main()` -- the one pipeline every caller uses.
    """
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)
    splits = assign_splits(cfg, graph, labels)
    cands = build_candidates(cfg, graph, scores, splits, labels)
    return graph, cands, labels


# --------------------------------------------------------------------------
# a held-out block shared by weight_policy.json and graphsage_policy.json
# (and, if a future run ever has a winner, xgboost_policy.json). Built
# entirely from evaluate()/expected_loss()/panel_verdict() -- no selection
# logic, just the single permitted read, formatted for the record.
# --------------------------------------------------------------------------


def _standard_held_out(cfg: Config, design: list[Candidate], test: list[Candidate],
                       labels: list[Label], threshold: float,
                       costs: dict[str, Any]) -> dict[str, Any]:
    ev = evaluate(cfg, test, labels, threshold)
    primary, secondary = ev["primary"], ev["secondary"]
    binary = expected_loss(test, threshold, costs)
    flag_all = expected_loss(test, 0.0, costs)
    fps = [c for c in test if c.score >= threshold and not c.is_positive]
    design_v = panel_verdict(cfg, design)
    return {
        "note": "The single permitted read, taken after the policy was frozen.",
        "n_components": len(test),
        "threshold": threshold,
        "precision": primary["precision"],
        "recall": primary["recall"],
        "f1": primary["f1"],
        "false_positive_rate": primary["false_positive_rate"],
        "tp": primary["tp"], "fp": primary["fp"],
        "tn": primary["tn"], "fn": primary["fn"],
        "rings_recovered": primary["rings_recovered"],
        "rings_in_test": primary["rings_in_test"],
        "expected_loss": binary["expected_loss"],
        "review_rate": binary["review_rate"],
        "review_cost": binary["review_cost"],
        "flag_everything_expected_loss": flag_all["expected_loss"],
        "false_positives_family": sum(1 for c in fps if c.has_family),
        "false_positives_background": sum(1 for c in fps if not c.has_family),
        "account_level": {
            "precision": secondary["precision"],
            "recall": secondary["recall"],
            "f1": secondary["f1"],
            "false_positive_rate": secondary["false_positive_rate"],
        },
        "design_panel_verdict_at_selection": design_v["verdict"],
        "design_positives_below_max_negative": design_v["positives_below_max_negative"],
    }


# --------------------------------------------------------------------------
# weights
# --------------------------------------------------------------------------

# The grid weight_search_protocol.md requires: FN_ABSORBED_FRACTION x
# FP_FRICTION_RATE, both varied around costmodel.py's declared defaults
# (1.00, 0.02). select_weights() takes a `costs` dict as a plain argument, so
# this sweep is composition -- repeated calls with a different costs dict --
# not a change to selection semantics. derive_costs() itself now takes both
# as optional parameters (defaulting to the declared constants) precisely so
# this sweep can call it once per grid cell rather than re-deriving its
# arithmetic here.
_FN_ABSORBED_FRACTIONS = (0.5, 0.75, 1.0)
_FP_FRICTION_RATES = (0.01, 0.02, 0.05)


def _weight_sensitivity(cfg: Config, design: list[Candidate]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fn_fraction in _FN_ABSORBED_FRACTIONS:
        for fp_rate in _FP_FRICTION_RATES:
            variant = derive_costs(design, fn_fraction, fp_rate)
            result = select_weights(cfg, design, variant)
            winner = result["winner"]
            row: dict[str, Any] = {
                "fn_absorbed_fraction": fn_fraction,
                "fp_friction_rate": fp_rate,
                "winner": winner,
                "expected_loss": result["winner_expected_loss"],
                "threshold": result["winner_threshold"],
                "feasible": result["feasible"],
            }
            ties = [r["policy"] for r in result["candidates"]
                    if r["policy"] != winner and r.get("feasible")
                    and r.get("expected_loss") == result["winner_expected_loss"]]
            if ties:
                row["exact_tie_with"] = ties[0]
            rows.append(row)
    distinct = sorted({r["winner"] for r in rows if r["winner"] is not None})
    return {
        "grid": "FN_ABSORBED_FRACTION x FP_FRICTION_RATE, as required by the protocol",
        "rows": rows,
        "distinct_winners": distinct,
        "winner_stable": len(distinct) <= 1,
    }


def freeze_weights(cfg: Config | None = None, path: Path | None = None) -> dict[str, Any]:
    cfg = cfg or Config()
    path = path or WEIGHT_POLICY

    _, cands, labels = _build(cfg)
    design = [c for c in cands if c.split in DESIGN_SPLITS]
    costs = derive_costs(design)

    meta = select_weights(cfg, design, costs)
    meta["sensitivity"] = _weight_sensitivity(cfg, design)
    freeze_policy(path, meta)

    if meta["winner"] is None:
        print("weights: no feasible candidate -- no held-out read taken")
        return meta

    # Recompute the winner's weight vector at full precision -- meta's own
    # "weights" field is rounded to 4dp for the record (sums to 0.9999, not
    # 1.0), which Config.__post_init__ rejects. The candidate FUNCTIONS in
    # costmodel.CANDIDATES are the source of truth; calling the winner's
    # again is not new selection logic, it is the exact call select_weights()
    # itself already made for this candidate.
    winner_weights = WEIGHT_CANDIDATES[meta["winner"]](cfg, design)
    rescored = rescore(cfg, winner_weights)
    design_r = [c for c in rescored if c.split in DESIGN_SPLITS]
    test = evaluate_frozen_policy(rescored, path)
    meta["held_out"] = _standard_held_out(
        cfg, design_r, test, labels, meta["winner_threshold"], costs
    )
    freeze_policy(path, meta)
    return meta


# --------------------------------------------------------------------------
# abstention
# --------------------------------------------------------------------------

_BINARY_THRESHOLD_NOTE = (
    "Not reused as a fixed boundary. t_lo and t_hi were both freely searched; "
    "this value is recorded only so a reader can see where the free search "
    "landed relative to the frozen binary policy."
)
_HELD_OUT_READ_NOTE = (
    "TAKEN, once, through evaluate_frozen_abstention_policy() after this file "
    "was frozen. No further read is permitted under this record."
)


def _per_action_scores(test: list[Candidate], t_lo: float, t_hi: float) -> dict[str, Any]:
    groups: dict[str, dict[str, list[float]]] = {
        a: {"positives": [], "negatives": []} for a in ("allow", "review", "escalate")
    }
    for c in test:
        action = "allow" if c.score < t_lo else "review" if c.score < t_hi else "escalate"
        key = "positives" if c.is_positive else "negatives"
        groups[action][key].append(round(c.score, 6))
    for g in groups.values():
        g["positives"].sort()
        g["negatives"].sort()
    return groups


def _sample_variance_note(t_lo: float, t_hi: float, val_tp: int, val_fp: int,
                          val_fn: int, val_tn: int, threshold: float,
                          n_test: int, review_rate: float,
                          loss_delta_vs_binary: float,
                          improvement_pct: float) -> str:
    if t_lo != t_hi:
        return (
            f"The band search this run selected a non-degenerate Review band "
            f"[{t_lo:.2f}, {t_hi:.2f}), read once against {n_test} held-out test "
            f"components: {review_rate:.1%} of them landed in Review, and the "
            f"band beats the binary policy on these same rows by "
            f"{abs(loss_delta_vs_binary):,.2f} expected loss ({improvement_pct}% "
            "lower). Both that figure and the separate 41.1% expected-loss "
            "improvement GraphSAGE reports over Tier 1 (graphsage_protocol.md "
            "§5) are single point estimates on the same n=112 test split, "
            "not distributions -- treat them as estimates with real but bounded "
            "uncertainty at this sample size, not as precise deltas. The bound is "
            "concrete, not hand-waved: the percentile-bootstrap CIs already "
            "computed for Tier 1's F1 on this same 112-component split (README, "
            "“95%-CI”) show a one- or two-component swing in the "
            "resample moving point estimates by roughly ±0.17-0.18 -- the "
            "same small-n mechanism applies here, since this band's read shares "
            "the identical test set and was likewise taken once, not resampled. "
            "Report this band's numbers as a central estimate on 112 components, "
            "not as a guarantee that a different draw lands the same way."
        )
    return (
        f"The band search this run selected t_lo == t_hi == {t_lo:.2f} -- a "
        "degenerate, zero-width Review band, identical to the binary policy. "
        f"A_baseline already reaches tp {val_tp} / fp {val_fp} / fn {val_fn} / "
        f"tn {val_tn} on validation at {threshold:.2f}, so there is no false "
        "positive to waive and no missed positive to rescue by widening Review "
        "in either direction -- an unconstrained sweep found nothing worth "
        "deferring to a human. This is a structural finding, not an error: it "
        "is the extreme case of the same mechanism the original and Phase 11 "
        "runs reported in weaker form (fn = 0 leaves nothing for Review to "
        "rescue below the threshold), taken all the way to fp = 0 as well this "
        "time, so there is nothing for it to waive above the threshold either."
    )


def _d3_sensitivity(t_lo: float, t_hi: float, binary_loss: float,
                    three_way_loss: float) -> dict[str, Any]:
    note = (
        "RESOLVED in Phase 10/11 (deferred_decisions.md D3): C_fp no longer "
        "carries an embedded review term, so the generic (tp+fp)*C_review "
        "term prices the review exactly once per flagged component. There is "
        "one cost model, not two under separate accountings -- this field is "
        "retained for API/shape compatibility."
    )
    if t_lo == t_hi:
        note += (
            " Both figures are identical this run because the selected band "
            "is degenerate (t_lo == t_hi), so the three-way and binary "
            "policies coincide exactly on these rows."
        )
    delta = round(binary_loss - three_way_loss, 2)
    improvement = round(delta / binary_loss * 100, 1) if binary_loss else 0.0
    return {
        "note": note,
        "binary_expected_loss_d3_corrected": binary_loss,
        "three_way_expected_loss_unchanged": three_way_loss,
        "loss_delta_d3_corrected": delta,
        "improvement_as_reported": f"{improvement}%",
        "improvement_d3_corrected": f"{improvement}%",
    }


def _abstention_held_out(test: list[Candidate], t_lo: float, t_hi: float,
                         costs: dict[str, Any],
                         weight_record: dict[str, Any]) -> dict[str, Any]:
    from .abstention import three_way_stats

    n_pos = sum(1 for c in test if c.is_positive)
    n_neg = len(test) - n_pos
    three = three_way_stats(test, t_lo, t_hi, costs)
    binary_threshold = weight_record["winner_threshold"]
    binary = expected_loss(test, binary_threshold, costs)
    winner_row = next(
        r for r in weight_record["candidates"] if r["policy"] == weight_record["winner"]
    )

    escalate_total = three["escalate_tp"] + three["escalate_fp"]
    precision = round(three["escalate_tp"] / escalate_total, 4) if escalate_total else 0.0
    recall_escalate_only = round(three["escalate_tp"] / n_pos, 4) if n_pos else 0.0
    recall_including_review = (
        round((three["escalate_tp"] + three["review_positives"]) / n_pos, 4) if n_pos else 0.0
    )
    fpr_escalate_only = round(three["escalate_fp"] / n_neg, 4) if n_neg else 0.0

    return {
        "note": "The single permitted read. Band read back from this file, not recomputed.",
        "n_components": three["n"],
        "band": {"t_lo": three["t_lo"], "t_hi": three["t_hi"]},
        "expected_loss": three["expected_loss"],
        "loss_per_component": three["loss_per_component"],
        "review_rate": three["review_rate"],
        "actions": {"allow": three["allow"], "review": three["review"],
                    "escalate": three["escalate"]},
        "by_action_and_label": {
            "allow_positive_missed": three["allow_missed_positives"],
            "allow_negative": three["allow"] - three["allow_missed_positives"],
            "review_positive": three["review_positives"],
            "review_negative": three["review_negatives"],
            "review_negative_family": three["review_family"],
            "escalate_positive": three["escalate_tp"],
            "escalate_negative": three["escalate_fp"],
        },
        "escalate_tier_metrics": {
            "precision": precision,
            "recall_escalate_only": recall_escalate_only,
            "recall_including_review": recall_including_review,
            "false_positive_rate_escalate_only": fpr_escalate_only,
            "note": f"{n_pos} test positives, {n_neg} test negatives. "
                    "recall_including_review counts a deferred ring as "
                    "caught-but-unconfirmed, not as detected.",
        },
        "binary_baseline_same_rows": {
            "threshold": binary_threshold,
            "expected_loss": binary["expected_loss"],
            "tp": binary["tp"], "fp": binary["fp"],
            "fn": binary["fn"], "tn": binary["tn"],
            "review_rate": binary["review_rate"],
        },
        "loss_delta_vs_binary": round(three["expected_loss"] - binary["expected_loss"], 2),
        "validation_expected_loss_for_reference": weight_record["winner_expected_loss"],
        "per_action_scores": _per_action_scores(test, t_lo, t_hi),
        "sample_variance_note": _sample_variance_note(
            t_lo, t_hi, winner_row["tp"], winner_row["fp"], winner_row["fn"],
            winner_row["tn"], binary_threshold,
            n_test=three["n"], review_rate=three["review_rate"],
            loss_delta_vs_binary=round(three["expected_loss"] - binary["expected_loss"], 2),
            improvement_pct=(
                round((binary["expected_loss"] - three["expected_loss"])
                      / binary["expected_loss"] * 100, 1)
                if binary["expected_loss"] else 0.0
            ),
        ),
        "d3_sensitivity": _d3_sensitivity(
            t_lo, t_hi, binary["expected_loss"], three["expected_loss"]
        ),
    }


def freeze_abstention(cfg: Config | None = None, weight_path: Path | None = None,
                      path: Path | None = None) -> dict[str, Any]:
    from .abstention import evaluate_frozen_abstention_policy, freeze_abstention_policy, select_abstention_band

    cfg = cfg or Config()
    weight_path = weight_path or WEIGHT_POLICY
    path = path or ABSTENTION_POLICY

    if not weight_path.exists():
        raise FileNotFoundError(
            f"{weight_path} is missing -- abstention is layered on the frozen "
            "A_baseline scorer, so `python -m riskmesh.freeze weights` must run "
            "(and produce a winner) before `abstention`."
        )
    weight_record = json.loads(weight_path.read_text(encoding="utf-8"))

    _, cands, _ = _build(cfg)
    design = [c for c in cands if c.split in DESIGN_SPLITS]
    costs = derive_costs(design)

    result = select_abstention_band(cfg, design, costs)
    meta: dict[str, Any] = {
        "protocol": "abstention_protocol.md",
        "scorer": "A_baseline (unchanged)",
        "binary_threshold_reference": weight_record["winner_threshold"],
        "binary_threshold_note": _BINARY_THRESHOLD_NOTE,
        "max_review_rate_gate": result["max_review_rate_gate"],
        "costs": costs,
        "result": result,
        "held_out_read": _HELD_OUT_READ_NOTE,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
    }
    freeze_abstention_policy(path, meta)

    test = evaluate_frozen_abstention_policy(cands, path)
    meta["held_out"] = _abstention_held_out(
        test, result["t_lo"], result["t_hi"], costs, weight_record
    )
    freeze_abstention_policy(path, meta)
    return meta


# --------------------------------------------------------------------------
# xgboost -- torch/xgboost imports stay INSIDE these two functions (G7)
# --------------------------------------------------------------------------


def freeze_xgboost(cfg: Config | None = None, path: Path | None = None) -> dict[str, Any]:
    from .ml import evaluate_frozen_ml_policy, freeze_ml_policy, select_xgboost_model

    cfg = cfg or Config()
    path = path or XGBOOST_POLICY

    _, cands, labels = _build(cfg)
    design = [c for c in cands if c.split in DESIGN_SPLITS]
    costs = derive_costs(design)

    meta = select_xgboost_model(cfg, design, costs)
    freeze_ml_policy(path, meta)

    if meta["winner"] is None:
        # Not an error: every candidate refused by the gate is a legitimate,
        # reportable outcome (xgboost_protocol.md SS6). No candidate to refit
        # means the protocol forbids reading the held-out split at all.
        print("xgboost: no feasible candidate -- no held-out read taken "
              "(every candidate was refused by the gate)")
        return meta

    # Full candidate list, not a pre-filtered test view -- the guard itself
    # filters split == "test" internally, symmetric with
    # costmodel.evaluate_frozen_policy() (G2).
    scored_test = evaluate_frozen_ml_policy(cfg, design, cands, path)
    meta["held_out"] = _standard_held_out(
        cfg, design, scored_test, labels, meta["winner_threshold"], costs
    )
    freeze_ml_policy(path, meta)
    return meta


def freeze_graphsage(cfg: Config | None = None, path: Path | None = None) -> dict[str, Any]:
    from .gnn import evaluate_frozen_gnn_policy, freeze_gnn_policy, select_gnn_model

    cfg = cfg or Config()
    path = path or GRAPHSAGE_POLICY

    graph, cands, labels = _build(cfg)
    design = [c for c in cands if c.split in DESIGN_SPLITS]
    costs = derive_costs(design)

    meta = select_gnn_model(cfg, design, graph, costs)
    freeze_gnn_policy(path, meta)

    if meta["winner"] is None:
        print("graphsage: no feasible candidate -- no held-out read taken "
              "(every candidate was refused by the gate)")
        return meta

    # Full candidate list, not a pre-filtered test view -- the guard itself
    # filters split == "test" internally, symmetric with
    # costmodel.evaluate_frozen_policy() (G2).
    scored_test = evaluate_frozen_gnn_policy(cfg, design, cands, graph, path)
    meta["held_out"] = _standard_held_out(
        cfg, design, scored_test, labels, meta["winner_threshold"], costs
    )
    freeze_gnn_policy(path, meta)
    return meta


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

STAGES = ("weights", "abstention", "xgboost", "graphsage")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m riskmesh.freeze")
    ap.add_argument("stage", choices=(*STAGES, "all"))
    args = ap.parse_args(argv)

    stages = STAGES if args.stage == "all" else (args.stage,)
    runners = {
        "weights": freeze_weights,
        "abstention": freeze_abstention,
        "xgboost": freeze_xgboost,
        "graphsage": freeze_graphsage,
    }
    paths = {
        "weights": WEIGHT_POLICY,
        "abstention": ABSTENTION_POLICY,
        "xgboost": XGBOOST_POLICY,
        "graphsage": GRAPHSAGE_POLICY,
    }
    for stage in stages:
        meta = runners[stage]()
        if stage == "abstention":
            band = meta["result"]
            status = f"band t_lo={band['t_lo']} t_hi={band['t_hi']}"
        else:
            status = f"winner={meta.get('winner')}"
        print(f"{stage}: wrote {paths[stage]}  {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
