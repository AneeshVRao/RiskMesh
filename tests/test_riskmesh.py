"""RiskMesh Tier 0 checks. Plain asserts, no framework:  python tests/test_riskmesh.py

Mirrors `testing.md`. Three groups:

  correctness      -- the pipeline does what it says (leakage, splits, hygiene)
  non-triviality   -- the benchmark is hard enough to mean anything
  pipeline         -- the threshold freeze is real and reproducible

Non-triviality runs on train+validation only, because those are the numbers a
generator would be tuned against and the PRD forbids tuning on test statistics.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riskmesh.config import SIGNALS, Config
from riskmesh.evaluate import (
    build_candidates,
    best_f1_with_direction,
    confusion,
    prf,
    select_threshold,
    shared_device_baseline_f1,
    single_signal_detail,
    single_signal_f1,
)
from riskmesh.generate import Label, accounts_per_attribute, generate
from riskmesh.graph import build_graph
from riskmesh.integrity import non_triviality_panel
from riskmesh.score import score_all
from riskmesh.split import assign_splits

PASSED: list[str] = []


def check(name: str) -> None:
    PASSED.append(name)
    print(f"  ok   {name}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(cfg: Config):
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)
    splits = assign_splits(cfg, graph, labels)
    cands = build_candidates(cfg, graph, scores, splits, labels)
    return txns, labels, graph, scores, splits, cands


# --------------------------------------------------------------------------
# correctness
# --------------------------------------------------------------------------


def test_01_determinism(cfg: Config, run_a: dict, run_b: dict) -> None:
    a, b = run_a["dir"] / "transactions.csv", run_b["dir"] / "transactions.csv"
    assert sha(a) == sha(b), "same seed produced different transactions"
    check("01 determinism: two runs at one seed give byte-identical transactions.csv")


def test_02_no_label_leakage(cfg: Config, run_a: dict) -> None:
    header = (run_a["dir"] / "transactions.csv").read_text(encoding="utf-8").splitlines()[0]
    cols = set(header.split(","))
    banned = {"ring_id", "cluster_id", "active_period", "is_ring", "label", "is_positive"}
    assert not (cols & banned), f"transactions.csv leaks labels: {cols & banned}"
    assert not (set(SIGNALS) & set(Label._fields)), "signal names collide with label fields"
    # The scorer must not be able to receive labels: (cfg, component, context).
    from inspect import signature

    from riskmesh.score import score_component

    params = set(signature(score_component).parameters)
    assert params == {"cfg", "comp", "ctx"}, f"score_component signature drifted: {params}"
    check("02 no label leakage: transactions.csv is label-free, scorer takes none")


def test_03_split_isolation(cands) -> None:
    seen: dict[str, str] = {}
    for c in cands:
        for key in ([c.ring_id] if c.ring_id else []):
            assert seen.get(key, c.split) == c.split, f"{key} spans splits"
            seen[key] = c.split
    check("03 split isolation: no ring appears in two splits")


def test_04_split_assignment_agrees(splits) -> None:
    labelled = [c for c in splits.by_component.values() if c.is_labelled]
    assert labelled, "no labelled components"
    bad = [c.component_id for c in labelled if c.active_period != c.median_period]
    assert not bad, f"active_period != median_timestamp_period for {bad}"
    check(f"04 split assignment: active_period == median period for all {len(labelled)}")


def test_05_hygiene(cfg: Config, txns, graph) -> None:
    n_accounts = len({t.account_id for t in txns})
    largest = max((c.size for c in graph.components), default=0)
    share = largest / n_accounts
    assert share < cfg.max_largest_component_share, f"giant component: {share:.1%}"

    per_ip = accounts_per_attribute(txns, "ip_id")
    nat = {ip for ip in per_ip if ip.startswith("ip_nat")}
    capped = set(graph.capped["ip_id"])
    assert nat <= capped, f"NAT IPs not capped: {sorted(nat - capped)}"
    check(f"05 hygiene: largest component {share:.1%} < {cfg.max_largest_component_share:.0%}, "
          f"all {len(nat)} NAT IPs capped")


def _shared_attr_types(accounts: set[str], txns) -> set[str]:
    """Attribute types this group of accounts genuinely shares."""
    out: set[str] = set()
    for attr in ("device_id", "ip_id", "instrument_id"):
        holders: dict[str, set[str]] = defaultdict(set)
        for t in txns:
            if t.account_id in accounts:
                holders[getattr(t, attr)].add(t.account_id)
        if any(len(v) >= 2 for v in holders.values()):
            out.add(attr)
    return out


def test_06_hard_negatives_are_hard(txns, labels) -> None:
    fams: dict[str, set[str]] = defaultdict(set)
    rings: dict[str, set[str]] = defaultdict(set)
    for lb in labels:
        if lb.cluster_id:
            fams[lb.cluster_id].add(lb.account_id)
        if lb.ring_id:
            rings[lb.ring_id].add(lb.account_id)

    ring_attrs: set[str] = set()
    for accts in rings.values():
        ring_attrs |= _shared_attr_types(accts, txns)

    for cid, accts in fams.items():
        shared = _shared_attr_types(accts, txns)
        assert shared & ring_attrs, (
            f"family {cid} shares {shared or 'nothing'}, rings share {ring_attrs} "
            "-- an easy negative, not a hard one"
        )
    check(f"06 hard negatives: all {len(fams)} families share {sorted(ring_attrs)} with rings")


def test_06b_inverse_direction_signals(cfg: Config, cands) -> None:
    """Regression: the max-F1 check must sweep BOTH threshold directions.

    A synthetic signal where only LOW values are suspicious. A `>=`-only sweep
    cannot separate it and reports a poor F1; the correct check finds perfect
    separation in the `<=` direction. This test fails if the evaluator is ever
    reverted to a one-directional sweep. See bugs.md RISK-001.
    """
    # low value == suspicious; perfectly separable at t=4 in the <= direction
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    actual = [True, True, True, True, False, False, False, False]

    f1, direction, threshold = best_f1_with_direction(values, actual)
    assert f1 == 1.0, f"inverse-direction separation missed: got F1 {f1}"
    assert direction == "<=", f"expected the <= direction to win, got {direction}"
    assert threshold == 4.0, f"expected threshold 4.0, got {threshold}"

    # Prove the test discriminates: a >=-only sweep must NOT find this. If this
    # assertion ever fails, the fixture stopped being inverse-direction and the
    # test above would pass even with a broken evaluator.
    up_only = max(
        prf(confusion([(v >= t, a) for v, a in zip(values, actual)]))["f1"]
        for t in sorted(set(values))
    )
    assert up_only < 0.95, (
        f">=-only sweep reaches F1 {up_only} on the inverse fixture -- the "
        "fixture no longer discriminates and this test proves nothing"
    )

    # And the real benchmark must actually contain inverted signals, otherwise
    # this whole class of bug is untested against live data.
    fit = [c for c in cands if c.split in ("train", "validation")]
    detail = single_signal_detail(fit)
    inverted = sorted(k for k, d in detail.items() if d["direction"] == "<=")
    assert inverted, "no inverted signals in the benchmark -- fixture-only coverage"
    check(f"06b inverse-direction: <= sweep finds F1 1.0 where >=-only gets "
          f"{up_only:.3f}; live inverted signals {inverted}")


# --------------------------------------------------------------------------
# non-triviality (train + validation only)
# --------------------------------------------------------------------------


def test_07_to_11_non_triviality(cfg: Config, cands) -> None:
    panel = non_triviality_panel(cfg, cands)
    checks = panel["checks"]

    assert checks["score_distributions_overlap"]["status"] == "PASS", (
        f"positive and negative scores do not overlap: {panel['score_overlap']}"
    )
    check("07 non-triviality: positive and negative score distributions overlap")

    frac = checks["positives_below_max_negative"]["value"]
    assert frac >= cfg.min_positive_below_max_negative_fraction, (
        f"only {frac:.0%} of positives fall below the top negative, "
        f"need {cfg.min_positive_below_max_negative_fraction:.0%}"
    )
    check(f"08 non-triviality: {frac:.0%} of positives below the top negative "
          f"(bound {cfg.min_positive_below_max_negative_fraction:.0%})")

    n_fam = checks["hard_negative_in_positive_range"]["value"]
    assert n_fam >= 1, "no family cluster reaches the positive score range"
    check(f"09 non-triviality: {n_fam} family clusters land inside the positive range")

    fit = [c for c in cands if c.split in ("train", "validation")]
    per_signal = single_signal_f1(fit)
    perfect = {k: v for k, v in per_signal.items() if v >= 1.0}
    assert not perfect, (
        f"single raw signal separates the classes perfectly: {perfect} -- "
        "the graph and the weighted scorer are decoration"
    )
    flagged = {k: v for k, v in per_signal.items() if v >= cfg.single_signal_flag_f1}
    check(f"10 non-triviality: no signal reaches F1 1.0 "
          f"(max {max(per_signal.values()):.3f}); flagged for review: {flagged or 'none'}")

    dev = shared_device_baseline_f1(fit)
    assert dev < cfg.max_shared_device_baseline_f1, (
        f"shared-device-only baseline reaches F1 {dev}, bound {cfg.max_shared_device_baseline_f1}"
    )
    check(f"11 non-triviality: shared-device-only baseline F1 {dev:.3f} "
          f"< {cfg.max_shared_device_baseline_f1}")


# --------------------------------------------------------------------------
# pipeline verification
# --------------------------------------------------------------------------


def test_12_to_17_pipeline(cfg: Config, run_a: dict, cands, labels) -> None:
    out = run_a["dir"]
    tj = out / "threshold.json"
    assert tj.exists(), "validation threshold was never persisted"
    import json

    frozen = json.loads(tj.read_text(encoding="utf-8"))
    assert frozen["selected_on"] == "validation"
    check(f"12 threshold persisted to threshold.json ({frozen['threshold']:.2f}, "
          f"on {frozen['validation_components']} validation components)")

    # Recompute the validation choice independently; it must match the file.
    validation = [c for c in cands if c.split == "validation"]
    recomputed, _ = select_threshold(cfg, validation)
    assert abs(recomputed - frozen["threshold"]) < 1e-9, (
        f"frozen threshold {frozen['threshold']} != validation choice {recomputed}"
    )
    check("13 test evaluation uses the frozen validation threshold, not a fresh one")

    report = run_a["eval"]
    assert abs(report["threshold"] - frozen["threshold"]) < 1e-9
    assert report["threshold_selected_on"] == "validation"
    check("14 threshold in eval_report.json equals the validation threshold")

    test = [c for c in cands if c.split == "test"]
    p = report["primary"]
    assert p["tp"] + p["fp"] + p["tn"] + p["fn"] == len(test), (
        f"confusion {p['tp']}+{p['fp']}+{p['tn']}+{p['fn']} != {len(test)} test components"
    )
    check(f"15 confusion matrix accounts for every one of {len(test)} test components")

    pos = [c for c in test if c.is_positive]
    neg = [c for c in test if not c.is_positive]
    assert pos, "test split has no positive ring component"
    check(f"16 test split contains {len(pos)} positive ring components")

    assert neg, "test split has no negative component"
    for name in cfg.split_boundaries:
        unlabelled = [
            c for c in cands
            if c.split == name and not c.is_positive and not c.has_family
        ]
        assert unlabelled, f"{name} split has no unlabelled background component"
    check(f"17 test split has {len(neg)} negatives; every split has unlabelled ones")


def test_18_reproducible_outputs(run_a: dict, run_b: dict) -> None:
    files = ["transactions.csv", "labels.csv", "components.csv",
             "integrity_report.json", "eval_report.json", "threshold.json"]
    for name in files:
        a, b = run_a["dir"] / name, run_b["dir"] / name
        assert a.exists(), f"{name} was never written"
        assert sha(a) == sha(b), f"{name} differs between two runs at the same seed"
    check(f"18 all {len(files)} output files reproduce byte-for-byte at the same seed")


def test_19_panel_gate_refuses_a_failing_weight_vector(cfg, cands) -> None:
    """The weight-search gates must REFUSE, not just report.

    bugs.md L2: held-out F1 rose to 0.8889 twice while the panel failed both
    times, so an infeasible weight vector must be structurally unable to receive
    an expected-loss figure. Three gates, all hard: panel PASS, hard negatives in
    the positive range >= 4, positives below the top negative >= 0.45. Panel PASS
    alone is necessary and not sufficient -- B_equal clears the panel and is
    still refused. This test fails if anyone relaxes any of them into a warning.
    """
    from riskmesh.costmodel import (CANDIDATES, MIN_HARD_NEGATIVES_IN_RANGE,
                                    MIN_POSITIVES_BELOW_MAX_NEGATIVE,
                                    PanelGateFailure, derive_costs,
                                    gated_expected_loss, panel_verdict, rescore)

    design = [c for c in cands if c.split in ("train", "validation")]
    costs = derive_costs(design)
    assert costs["false_negative"] > costs["false_positive"] > costs["manual_review"], (
        "derived costs are not ordered as a fraud cost model requires"
    )

    def feasible(v: dict) -> bool:
        return (v["verdict"] == "PASS"
                and v["hard_negatives_inside_positive_range"]
                >= MIN_HARD_NEGATIVES_IN_RANGE
                and v["positives_below_max_negative"]
                >= MIN_POSITIVES_BELOW_MAX_NEGATIVE)

    refused, scored = [], []
    for name, policy in CANDIDATES.items():
        view = [c for c in rescore(cfg, policy(cfg, design))
                if c.split in ("train", "validation")]
        v = panel_verdict(cfg, view)
        try:
            gated_expected_loss(cfg, view, 0.25, costs)
            scored.append(name)
            assert feasible(v), f"{name} was scored despite failing a gate: {v}"
        except PanelGateFailure:
            refused.append(name)
            assert not feasible(v), f"{name} was refused despite passing every gate"

    assert refused, (
        "no candidate was refused -- a gate that never fires has not been shown "
        "to work, and D_drop_flagged is on the candidate list precisely to fire it"
    )
    assert "D_drop_flagged" in refused, "the known-bad candidate was not refused"
    assert "B_equal" in refused, (
        "B_equal passes the non-triviality panel but drops hard negatives in the "
        "positive range from 4 to 1 -- the difficulty gate exists to refuse it, "
        "and if it no longer does, panel PASS has silently become sufficient"
    )
    assert "A_baseline" in scored, "the incumbent must remain feasible"
    check(f"19 weight gates refuse {sorted(refused)}, score {sorted(scored)}")


# --------------------------------------------------------------------------


def main() -> int:
    from riskmesh.__main__ import main as run_pipeline

    cfg = Config()
    tmp = Path(tempfile.mkdtemp(prefix="riskmesh_test_"))
    try:
        runs = []
        for i in ("a", "b"):
            d = tmp / i
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()):
                res = run_pipeline(cfg, out=d)
            runs.append({"dir": d, "eval": res["eval"], "integrity": res["integrity"]})
        run_a, run_b = runs

        txns, labels, graph, scores, splits, cands = build(cfg)

        print(f"\nRiskMesh Tier 0 checks  (seed {cfg.seed}, config {cfg.fingerprint()})\n")
        print("correctness")
        test_01_determinism(cfg, run_a, run_b)
        test_02_no_label_leakage(cfg, run_a)
        test_03_split_isolation(cands)
        test_04_split_assignment_agrees(splits)
        test_05_hygiene(cfg, txns, graph)
        test_06_hard_negatives_are_hard(txns, labels)
        test_06b_inverse_direction_signals(cfg, cands)

        print("\nnon-triviality (train + validation only)")
        test_07_to_11_non_triviality(cfg, cands)

        print("\npipeline verification")
        test_12_to_17_pipeline(cfg, run_a, cands, labels)
        test_18_reproducible_outputs(run_a, run_b)

        print("\nweight-search protocol (frozen, run, A_baseline retained)")
        test_19_panel_gate_refuses_a_failing_weight_vector(cfg, cands)

        print(f"\n{len(PASSED)}/20 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
