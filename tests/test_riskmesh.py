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
from collections import Counter, defaultdict
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


def test_01b_population_scale(cfg: Config, txns) -> None:
    """Transaction count tracks cfg.target_txns, not a literal (Task 3).

    Previously this bound only existed as a self-check in generate.py's own
    `__main__` block, which this suite never runs -- so the actual test suite
    had no check on population scale at all. Anchoring on cfg.target_txns
    (rather than a hardcoded count) keeps this meaningful whatever the
    population is later tuned to.
    """
    lo, hi = 0.9 * cfg.target_txns, 1.1 * cfg.target_txns
    assert lo <= len(txns) <= hi, (
        f"{len(txns)} transactions outside cfg.target_txns={cfg.target_txns} "
        f"+/-10% [{lo:.0f}, {hi:.0f}]"
    )
    check(f"01b population scale: {len(txns)} transactions within "
          f"cfg.target_txns={cfg.target_txns} +/-10%")


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
    """Task 4 (audit finding #16): `Candidate` now carries a `cluster_id`
    alongside `ring_id`, so this check covers hard-negative clusters too, not
    just rings -- closing the gap where the PRD's "legitimate hard-negative
    clusters remain within a single split" was claimed but never verified at
    the candidate level (split.py's own `_assert_no_cluster_spans_splits`
    already enforced it structurally; this is the independent check)."""
    seen: dict[str, str] = {}
    for c in cands:
        keys = ([c.ring_id] if c.ring_id else []) + ([c.cluster_id] if c.cluster_id else [])
        for key in keys:
            assert seen.get(key, c.split) == c.split, f"{key} spans splits"
            seen[key] = c.split
    check("03 split isolation: no ring or hard-negative cluster appears in two splits")


def test_03b_five_ring_types_present_and_split_isolated(labels) -> None:
    """Task 3: all five ring mechanisms exist, each ring is one type, and
    that type never spans two splits (a ring-level fact -- the ring's
    `active_period` IS its split, and every member agrees, so reading either
    off any one member's label is exact, not a majority vote)."""
    from riskmesh.generate import RING_TYPES

    types_seen = {lb.ring_type for lb in labels if lb.ring_id}
    assert types_seen == set(RING_TYPES), (
        f"expected all five ring types {sorted(RING_TYPES)}, saw {sorted(types_seen)}"
    )

    ring_type: dict[str, str] = {}
    ring_split: dict[str, str] = {}
    for lb in labels:
        if not lb.ring_id:
            continue
        assert ring_type.setdefault(lb.ring_id, lb.ring_type) == lb.ring_type, (
            f"{lb.ring_id} has members labelled with two different ring types"
        )
        assert ring_split.setdefault(lb.ring_id, lb.active_period) == lb.active_period, (
            f"{lb.ring_id} spans two splits (active_period disagrees across members)"
        )
    check(f"03b all five ring types present {sorted(types_seen)}; "
          f"each of {len(ring_type)} rings is one type inside exactly one split")


def test_03c_every_ring_type_yields_a_positive_candidate(cands, labels) -> None:
    """Task 3 review fix: label presence (03b) is not enough on its own.

    A ring type with no structural edge at all reduces to singleton accounts
    -- graph.py forms no component from merchant-only sharing -- and never
    becomes a scoreable candidate. It would then sit in labels.csv and
    nowhere else: present in ground truth, absent from every metric the
    panel and the scorer actually compute. This is exactly what happened to
    the first cut of the refund-abuse type (no device/ip/instrument edge at
    all): 0 of its rings survived as positive candidates in the design
    split. Asserted per type, not in aggregate, so one invisible type cannot
    hide behind the other four's counts.
    """
    from riskmesh.generate import RING_TYPES

    type_by_ring = {lb.ring_id: lb.ring_type for lb in labels if lb.ring_id}
    design = [c for c in cands if c.split in ("train", "validation")]
    pos_types = Counter(type_by_ring[c.ring_id] for c in design if c.is_positive)
    missing = [t for t in RING_TYPES if pos_types.get(t, 0) < 1]
    assert not missing, (
        f"ring type(s) {missing} contribute zero positive candidates to the "
        f"design split (counts: {dict(sorted(pos_types.items()))}) -- "
        "structurally undetectable"
    )
    check("03c every ring type yields >=1 positive design candidate: "
          f"{dict(sorted(pos_types.items()))}")


def test_03d_four_cluster_types_present_and_split_isolated(labels) -> None:
    """Task 4, mirrors 03b: all four hard-negative cluster mechanisms exist,
    each cluster is one type, and that type never spans two splits (a
    cluster-level fact -- the cluster's `active_period` IS its split, and
    every member agrees, so reading either off any one member's label is
    exact, not a majority vote)."""
    from riskmesh.generate import CLUSTER_TYPES

    types_seen = {lb.cluster_type for lb in labels if lb.cluster_id}
    assert types_seen == set(CLUSTER_TYPES), (
        f"expected all four cluster types {sorted(CLUSTER_TYPES)}, saw {sorted(types_seen)}"
    )

    cluster_type: dict[str, str] = {}
    cluster_split: dict[str, str] = {}
    for lb in labels:
        if not lb.cluster_id:
            continue
        assert cluster_type.setdefault(lb.cluster_id, lb.cluster_type) == lb.cluster_type, (
            f"{lb.cluster_id} has members labelled with two different cluster types"
        )
        assert cluster_split.setdefault(lb.cluster_id, lb.active_period) == lb.active_period, (
            f"{lb.cluster_id} spans two splits (active_period disagrees across members)"
        )
    check(f"03d all four cluster types present {sorted(types_seen)}; "
          f"each of {len(cluster_type)} clusters is one type inside exactly one split")


def test_03e_every_cluster_type_yields_a_candidate_component(cands, labels) -> None:
    """Task 4, mirrors 03c: label presence (03d) is not enough on its own.

    A cluster type with no structural edge at all reduces to singleton
    accounts -- graph.py forms no component from merchant-only sharing -- and
    never becomes a scoreable candidate, exactly what the refund-abuse ring
    type hit in Task 3 before its structural-edge fix (weak instrument
    sharers). Asserted per type, not in aggregate, so one invisible type
    cannot hide behind the other three's counts. Unlike 03c, this does not
    require the candidate to be POSITIVE -- clusters are never "positive",
    only rings are -- it only requires that graph.py formed a component
    containing that cluster's accounts at all, in any split.
    """
    from riskmesh.generate import CLUSTER_TYPES

    type_by_cluster = {lb.cluster_id: lb.cluster_type for lb in labels if lb.cluster_id}
    seen_types = Counter(type_by_cluster[c.cluster_id] for c in cands if c.cluster_id)
    missing = [t for t in CLUSTER_TYPES if seen_types.get(t, 0) < 1]
    assert not missing, (
        f"cluster type(s) {missing} contribute zero candidate components "
        f"(counts: {dict(sorted(seen_types.items()))}) -- structurally undetectable"
    )
    check("03e every cluster type yields >=1 candidate component: "
          f"{dict(sorted(seen_types.items()))}")


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
    """Task 4 (audit finding #8): the check below asserts that each cluster
    shares AT LEAST ONE attribute type with SOME ring -- `shared & ring_attrs`
    is non-empty. `ring_attrs` itself is the UNION of attribute types shared
    across every ring type (typically device_id, ip_id, and instrument_id all
    at once, since the five ring mechanisms between them cover all three).
    The message below used to read as if every cluster shared the whole union
    with every ring, which the assertion never checked and is not true of any
    individual cluster type (office shares device+ip, hostel shares ip only,
    retail shares a weak instrument overlap only) -- fixed to describe what is
    actually asserted."""
    clusters: dict[str, set[str]] = defaultdict(set)
    rings: dict[str, set[str]] = defaultdict(set)
    for lb in labels:
        if lb.cluster_id:
            clusters[lb.cluster_id].add(lb.account_id)
        if lb.ring_id:
            rings[lb.ring_id].add(lb.account_id)

    ring_attrs: set[str] = set()
    for accts in rings.values():
        ring_attrs |= _shared_attr_types(accts, txns)

    for cid, accts in clusters.items():
        shared = _shared_attr_types(accts, txns)
        assert shared & ring_attrs, (
            f"cluster {cid} shares {shared or 'nothing'}, rings collectively share "
            f"{ring_attrs} -- an easy negative, not a hard one"
        )
    check(f"06 hard negatives: each of {len(clusters)} clusters shares >=1 of "
          f"rings' shared-attribute union {sorted(ring_attrs)} with some ring "
          "(not that every cluster shares all of it)")


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
    assert n_fam >= 1, "no hard-negative cluster reaches the positive score range"
    check(f"09 non-triviality: {n_fam} hard-negative clusters land inside the positive range")

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
             "integrity_report.json", "eval_report.json", "threshold.json",
             "graph_edges.json", "weight_policy.json",
             "abstention_policy.json", "baselines.json", "ablations.json",
             "bootstrap_ci.json"]
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
    # Phase 10 (D3): C_fp dropped its own embedded review term -- it is
    # friction-only now, since the generic (tp+fp)*C_review term already
    # prices one review per flagged component. That removes any structural
    # guarantee that C_fp > C_review (the old C_fp = review + friction made
    # that trivially true); what a fraud cost model still requires is that a
    # missed ring costs more than either a false-positive's friction or a
    # single review.
    assert costs["false_negative"] > costs["false_positive"], (
        "derived costs are not ordered as a fraud cost model requires"
    )
    assert costs["false_negative"] > costs["manual_review"], (
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
        "to work, and B_equal is on the candidate list precisely to fire it"
    )
    # Phase 10: D_drop_flagged zeros instrument_sharing and
    # merchant_concentration (RISK-004, RISK-002), but leaves the new
    # instrument_pool_concentration signal active -- unlike instrument_sharing,
    # it is not a filed defect, so dropping only the flagged pair no longer
    # removes all instrument-dimension signal from the scorer. Renormalising
    # onto the remaining (working) signals now clears both difficulty gates
    # (hard_negatives_inside_positive_range 6, positives_below_max_negative
    # 0.625 on train+validation). This is the intended effect of fixing
    # RISK-004's instrument dimension, not a gate regression -- the gate still
    # fires on B_equal below.
    assert "D_drop_flagged" in scored, (
        "D_drop_flagged should now be feasible: it only zeros the flagged "
        "instrument_sharing/merchant_concentration pair, and the new "
        "instrument_pool_concentration signal (not a filed defect) still "
        "carries the instrument dimension"
    )
    assert "B_equal" in refused, (
        "B_equal passes the non-triviality panel but takes "
        "positives_below_max_negative below the 0.45 difficulty gate -- the "
        "gate exists to refuse it, and if it no longer does, panel PASS has "
        "silently become sufficient"
    )
    assert "A_baseline" in scored, "the incumbent must remain feasible"
    check(f"19 weight gates refuse {sorted(refused)}, score {sorted(scored)}")


def test_20_abstention_binary_collapse(cfg, cands) -> None:
    """three_way_stats(t_lo=t_hi) must be bit-for-bit costmodel.expected_loss().

    abstention_protocol.md's entire cost formula is a strict generalisation of
    the binary one: at t_lo == t_hi the Review band is empty, Allow is the old
    negative-predicted set and Escalate is the old positive-predicted set. This
    is a permanent test, not a design-doc claim, because a future edit to
    either formula that breaks the equivalence would silently make the two
    cost models inconsistent with each other. The frozen number itself --
    107,168.10 at threshold 0.18 (re-derived in Task 3: first for the
    population raise and four new ring types, 4,000.00 -> 257,592.45; then
    again for the review fix that gave refund-abuse rings a structural edge
    so they survive as candidates, 257,592.45 -> 203,290.09; re-derived twice
    more in Task 4 -- once for the three new hard-negative cluster types and
    the further population raise, 203,290.09 -> 144,846.28, and again for
    the review fix that gave every retail member (not just 2 sampled
    sharers) a shared instrument so graph.py stops dropping most of each
    retail cluster as unconnected singletons, 144,846.28 -> 145,123.30 --
    see task-3-report.md and task-4-report.md; re-derived once more in Task 6
    when weight_search_protocol.md's fold-back rule changed
    Config()._default_weights() itself -- E_drop_temporal beat the old
    incumbent and was folded in, 145,123.30 -> 107,168.10 -- see
    weight_search_protocol.md SS8 and task-6-report.md) -- is asserted
    directly, not just the equality of the two formulas, so a regression in
    the pipeline upstream of the formulas is caught too. The number itself is
    not otherwise load-bearing; it is a regression anchor, and it is expected
    to move again whenever Config's population, ring mix, weights, or cost
    inputs change.
    """
    from riskmesh.abstention import three_way_stats
    from riskmesh.costmodel import derive_costs, expected_loss

    design = [c for c in cands if c.split in ("train", "validation")]
    validation = [c for c in design if c.split == "validation"]
    costs = derive_costs(design)

    binary = expected_loss(validation, 0.18, costs)
    three_way = three_way_stats(validation, 0.18, 0.18, costs)

    assert three_way["review"] == 0, "t_lo == t_hi must leave the Review band empty"
    assert three_way["expected_loss"] == binary["expected_loss"], (
        f"three-way formula at t_lo=t_hi=0.18 gives {three_way['expected_loss']}, "
        f"binary costmodel.expected_loss() gives {binary['expected_loss']} -- "
        "the collapse abstention_protocol.md relies on is broken"
    )
    assert three_way["expected_loss"] == 107168.1, (
        f"got {three_way['expected_loss']}, expected the frozen 107,168.10 -- "
        "either the formula or something upstream of it has changed"
    )
    check("20 abstention three_way_stats(t_lo=t_hi=0.18) reproduces the frozen "
          "binary expected loss 107,168.10 exactly")


def test_21_ablation_full_row_reproduces_the_shipped_eval(run_a: dict) -> None:
    """The ablation's `full` row must equal `eval_report.json` exactly.

    It is built by rescoring from scratch rather than reusing the pipeline's
    candidates, precisely so this can be asserted. If the two disagree, then a
    difference between ablation rows is not attributable to the removed group --
    it could be anything the rescore path does differently -- and the whole table
    stops meaning what it claims.
    """
    import json

    abl = json.loads((run_a["dir"] / "ablations.json").read_text(encoding="utf-8"))
    full = next(r for r in abl["configurations"] if r["group"] == "full")
    shipped = run_a["eval"]["primary"]
    for key in ("tp", "fp", "tn", "fn", "precision", "recall", "f1",
                "false_positive_rate"):
        assert full["held_out"][key] == shipped[key], (
            f"ablation 'full' row disagrees with eval_report on {key}: "
            f"{full['held_out'][key]} vs {shipped[key]} -- the rescore path does "
            f"not reproduce the shipped scorer, so no row in this table is "
            f"attributable to its removed group"
        )
    assert full["threshold"] == run_a["eval"]["threshold"]
    check("21 ablation 'full' row reproduces eval_report.json exactly "
          f"(F1 {full['held_out']['f1']:.4f} @ {full['threshold']})")


def test_22_ablation_groups_partition_the_signals(run_a: dict) -> None:
    """Every signal in exactly one group, and the predicted `ip` no-op held.

    implementation_plan.md predicted before the run that ablating `ip` would come
    out byte-identical to the full model, because RISK-001 already set that
    weight to 0.0 and renormalising a zero changes nothing. A difference would
    have been a renormalisation bug, not a finding -- so it is asserted rather
    than admired.
    """
    import json

    from riskmesh.comparisons import ABLATION_GROUPS

    covered: list[str] = []
    for group in ABLATION_GROUPS.values():
        covered.extend(group)
    assert sorted(covered) == sorted(SIGNALS), (
        f"ABLATION_GROUPS does not partition SIGNALS: {sorted(covered)}"
    )

    abl = json.loads((run_a["dir"] / "ablations.json").read_text(encoding="utf-8"))
    groups = {r["group"] for r in abl["configurations"]}
    assert groups == {"full", *ABLATION_GROUPS}, f"missing ablation rows: {groups}"

    ip = next(r for r in abl["configurations"] if r["group"] == "ip")
    assert ip["weight_removed"] == 0.0, (
        f"ip_sharing carries weight {ip['weight_removed']} -- RISK-001 zeroed it, "
        f"so either the risk was reopened without updating this test or the "
        f"weights on disk are not the ones RISK-001 left behind"
    )
    assert ip["identical_to_full"], (
        "ablating ip_sharing changed the result, but its weight is 0.0 -- "
        "renormalising a zero must be a no-op. This is a bug in _renormalised, "
        "not a finding about the IP signal."
    )
    check(f"22 ablation groups partition all {len(SIGNALS)} signals; the "
          "predicted ip no-op holds exactly")


SWEPT_BASELINES = ("random", "shared_device_only", "shared_ip_only",
                   "transaction_level", "ring_score")


def test_23_baselines_cover_the_five_the_prd_names(run_a: dict) -> None:
    """All five value-swept PRD row-63 baselines present, and none fitted on test.

    The cutoff-fitting guard is asserted by calling `_freeze_cutoff` with test
    rows and requiring it to raise. A protocol that is merely followed by
    convention is one refactor from being broken silently.
    """
    import json

    from riskmesh.comparisons import _freeze_cutoff

    base = json.loads((run_a["dir"] / "baselines.json").read_text(encoding="utf-8"))
    names = [b["baseline"] for b in base["baselines"]]
    assert names[:5] == list(SWEPT_BASELINES), f"expected {SWEPT_BASELINES}, got {names[:5]}"

    for b in base["baselines"]:
        if b["baseline"] not in SWEPT_BASELINES:
            continue
        assert b["validation_components"] > 0
        assert b["held_out"]["tp"] + b["held_out"]["fp"] + b["held_out"]["tn"] \
            + b["held_out"]["fn"] > 0, f"{b['baseline']} read no held-out rows"

    _, _, _, _, _, cands = build(Config())
    test_rows = [c for c in cands if c.split == "test"]
    try:
        _freeze_cutoff(test_rows, {c.component_id: c.score for c in test_rows})
    except AssertionError:
        pass
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError(
            "_freeze_cutoff accepted test candidates -- a baseline could be "
            "fitted on held-out data without anything complaining"
        )
    check(f"23 all five value-swept PRD baselines present and read once; "
          f"_freeze_cutoff refuses test rows")


def test_24_shipped_scorer_is_not_re_swept_in_the_baseline_table(run_a: dict) -> None:
    """The `ring_score` row is the shipped freeze, not a re-swept variant.

    The four challengers sweep their cutoff over observed values, which is
    strictly finer than select_threshold()'s 0.01 grid. Granting the incumbent
    the same finer sweep would put a number on the Benchmark tab that differs
    from the one in eval_report.json for the same detector -- and would flatter
    it, since the finer sweep scored 0.8421 against the shipped 0.8000.
    """
    import json

    base = json.loads((run_a["dir"] / "baselines.json").read_text(encoding="utf-8"))
    ring = next(b for b in base["baselines"] if b["baseline"] == "ring_score")
    assert ring["cutoff"] == run_a["eval"]["threshold"], (
        f"baseline table reports the shipped scorer at cutoff {ring['cutoff']} "
        f"but it ships at {run_a['eval']['threshold']}"
    )
    assert ring["held_out"]["f1"] == run_a["eval"]["primary"]["f1"], (
        f"baseline table reports held-out F1 {ring['held_out']['f1']} for the "
        f"shipped scorer; eval_report says {run_a['eval']['primary']['f1']}"
    )
    check("24 baseline table reports the shipped scorer at its own frozen "
          f"threshold ({ring['cutoff']}, F1 {ring['held_out']['f1']:.4f})")


def test_25_baseline_table_has_seven_rows_tier2_refused_tier3_present(run_a: dict) -> None:
    """PRD baselines 6 and 7 (Task 7a): both tiers are complete, so both rows
    must be present -- Tier 2 (no feasible candidate) as an explicit refusal
    with no fabricated metric (G5), Tier 3 (a winner) with its real held-out
    read, sourced from experiments/xgboost_policy.json and
    experiments/graphsage_policy.json verbatim, never refit or re-scored.

    Coordinator correction: `tier1_reference` must be weight_policy.json's OWN
    held_out block (Tier 1 at ITS cost-selected threshold 0.10, F1 0.5432,
    loss 92,263.55) -- NOT baselines.json's `ring_score` row (Tier 1 at a
    DIFFERENT, independently validation-swept cutoff 0.22, F1 0.75). An
    earlier version of this check asserted the latter, which is exactly the
    mixed-operating-point pairing the coordinator flagged as wrong; every
    metric asserted below carries the threshold it was measured at so that
    mistake cannot silently recur.
    """
    import json

    base = json.loads((run_a["dir"] / "baselines.json").read_text(encoding="utf-8"))
    names = [b["baseline"] for b in base["baselines"]]
    assert names == list(SWEPT_BASELINES) + ["xgboost_scorer", "gnn_scorer"], names

    xg = json.loads(Path("experiments/xgboost_policy.json").read_text(encoding="utf-8"))
    gs = json.loads(Path("experiments/graphsage_policy.json").read_text(encoding="utf-8"))
    wp = json.loads(Path("experiments/weight_policy.json").read_text(encoding="utf-8"))

    tier2 = next(b for b in base["baselines"] if b["baseline"] == "xgboost_scorer")
    assert xg["winner"] is None, "xgboost_policy.json now has a winner -- update the fixture"
    assert tier2["feasible"] is False
    assert tier2["held_out"] is None, "no feasible candidate means no held-out read"
    assert "refused" in tier2["status"] and "no held-out read" in tier2["status"]
    assert tier2["candidates_tried"] == len(xg["candidates"]) == 4
    assert set(tier2["refusal_reasons"]) == set(xg["infeasible"])

    tier3 = next(b for b in base["baselines"] if b["baseline"] == "gnn_scorer")
    assert tier3["feasible"] is True
    assert tier3["winner"] == gs["winner"] == "G2_two_layer"
    assert tier3["held_out"]["threshold"] == gs["winner_threshold"]
    assert tier3["held_out"]["f1"] == gs["held_out"]["f1"]
    assert tier3["held_out"]["expected_loss"] == gs["held_out"]["expected_loss"]

    ref = tier3["tier1_reference"]
    assert ref["threshold"] == wp["held_out"]["threshold"] == 0.1, ref
    assert ref["f1"] == wp["held_out"]["f1"], ref
    assert ref["expected_loss"] == wp["held_out"]["expected_loss"], ref
    ring = next(b for b in base["baselines"] if b["baseline"] == "ring_score")
    assert ref["f1"] != ring["held_out"]["f1"], (
        "tier1_reference must be weight_policy.json's own cost-selected read, "
        "not ring_score's independently-swept F1 at a different cutoff -- "
        "these two happen to differ in this benchmark, which is exactly what "
        "makes mixing them detectable"
    )

    check(f"25 baseline table carries all seven PRD baselines; Tier 2 refused "
          f"explicitly ({tier2['candidates_tried']} candidates, no held-out read); "
          f"Tier 3 winner {tier3['winner']} held-out F1 {tier3['held_out']['f1']} "
          f"@ {tier3['held_out']['threshold']} vs Tier 1 F1 {ref['f1']} @ "
          f"{ref['threshold']} (same-operating-point pair, loss "
          f"{tier3['held_out']['expected_loss']:,.2f} vs {ref['expected_loss']:,.2f})")


def test_26_threshold_sweep_has_six_columns_on_validation_only(run_a: dict) -> None:
    """PRD False-Positive Cost Model -> Threshold Analysis (Task 7b): a real
    sweep across the threshold grid, all six named columns on every row,
    computed on validation only (G2), with the shipped operating point marked.
    """
    import json
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from riskmesh.api.artifacts import Artifacts
    from riskmesh.api import payloads

    a = Artifacts(run_a["dir"])
    sweep = payloads.threshold_analysis(a)["sweep"]
    assert sweep["computed_on"] == "validation"
    assert sweep["n_components"] == len(a.in_split("validation"))
    required_cols = {"threshold", "precision", "recall", "false_positive_count",
                      "false_positive_rate", "false_negative_count",
                      "false_negative_rate", "manual_reviews",
                      "manual_review_rate", "expected_loss", "selected"}
    assert len(sweep["grid"]) == 101, len(sweep["grid"])
    for row in sweep["grid"]:
        assert required_cols <= set(row), required_cols - set(row)

    selected_rows = [r for r in sweep["grid"] if r["selected"]]
    assert len(selected_rows) == 1, selected_rows
    threshold_json = json.loads((run_a["dir"] / "threshold.json").read_text(encoding="utf-8"))
    assert selected_rows[0]["threshold"] == threshold_json["threshold"]

    # Ladder unchanged -- still four rows, still the only field the UI reads.
    ladder_names = [r["policy"] for r in payloads.threshold_analysis(a)["ladder"]]
    assert ladder_names == ["flag_nothing", "flag_everything", "binary", "three_way"]

    check(f"26 threshold sweep: {len(sweep['grid'])} rows on validation only, "
          f"all six PRD columns present, operating point {selected_rows[0]['threshold']} "
          f"marked; 4-row ladder unchanged")


def test_27_bootstrap_ci_reproducible_and_reported_honestly(run_a: dict, run_b: dict) -> None:
    """PRD Metric Uncertainty (Task 7c): bootstrap CIs for precision, recall,
    F1, false-positive rate, reproducible under a seed derived from cfg.seed,
    reported as percentile intervals even when wide (n=112 test components).
    """
    import json

    ci_a = json.loads((run_a["dir"] / "bootstrap_ci.json").read_text(encoding="utf-8"))
    ci_b = json.loads((run_b["dir"] / "bootstrap_ci.json").read_text(encoding="utf-8"))
    assert ci_a == ci_b, "bootstrap CI is not reproducible at a fixed seed"

    required = {"precision", "recall", "f1", "false_positive_rate"}
    assert set(ci_a["metrics"]) == required, ci_a["metrics"]
    for name, m in ci_a["metrics"].items():
        assert m["ci_low"] <= m["point_estimate"] <= m["ci_high"], (name, m)
        assert m["width"] == round(m["ci_high"] - m["ci_low"], 4)
    # Deliberately a literal: this catches a regression in component FORMATION
    # (e.g. a graph.py bug) that a config-fingerprint match cannot detect --
    # same justification as test_api.py's len(a.components) == 336 check.
    assert ci_a["n_components"] == 112, ci_a["n_components"]
    # Honesty check, not a tightness requirement: the PRD explicitly allows a
    # wide interval to be the finding at this sample size -- this asserts the
    # interval is reported (non-degenerate point-mass), not that it is narrow.
    assert ci_a["metrics"]["f1"]["width"] > 0.0, (
        "a zero-width interval at n=112 would suggest resampling never varied "
        "the sample -- almost certainly a bug, not a genuinely tight estimate"
    )

    check(f"27 bootstrap CI byte-identical across two runs at the same seed "
          f"({ci_a['n_resamples']} resamples); F1 {ci_a['metrics']['f1']['point_estimate']} "
          f"CI [{ci_a['metrics']['f1']['ci_low']}, {ci_a['metrics']['f1']['ci_high']}] "
          f"width {ci_a['metrics']['f1']['width']} reported as-is")


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
        test_01b_population_scale(cfg, txns)
        test_02_no_label_leakage(cfg, run_a)
        test_03_split_isolation(cands)
        test_03b_five_ring_types_present_and_split_isolated(labels)
        test_03c_every_ring_type_yields_a_positive_candidate(cands, labels)
        test_03d_four_cluster_types_present_and_split_isolated(labels)
        test_03e_every_cluster_type_yields_a_candidate_component(cands, labels)
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

        print("\nabstention protocol (binary-collapse invariant at t_lo=t_hi=0.18 -- "
              "a fixed regression-anchor threshold, independent of whatever band "
              "abstention_protocol.md currently freezes, see its SS8)")
        test_20_abstention_binary_collapse(cfg, cands)

        print("\nbaselines and ablation (PRD rows 63 and 70, frozen then run)")
        test_21_ablation_full_row_reproduces_the_shipped_eval(run_a)
        test_22_ablation_groups_partition_the_signals(run_a)
        test_23_baselines_cover_the_five_the_prd_names(run_a)
        test_24_shipped_scorer_is_not_re_swept_in_the_baseline_table(run_a)

        print("\nTask 7: XGBoost/GraphSAGE baseline rows, threshold sweep, bootstrap CI")
        test_25_baseline_table_has_seven_rows_tier2_refused_tier3_present(run_a)
        test_26_threshold_sweep_has_six_columns_on_validation_only(run_a)
        test_27_bootstrap_ci_reproducible_and_reported_honestly(run_a, run_b)

        print(f"\n{len(PASSED)}/33 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
