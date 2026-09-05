"""API data-layer checks. Stdlib only -- runs without FastAPI installed.

The web layer is thin (routes.py just calls payloads). What actually needs
proving is that the reshaped payloads still carry the frozen numbers, that the
API's two derived formulas agree with the pipeline's own, and that the peer rule
is deterministic. All of that is reachable without starting a server.

Run:  python tests/test_api.py
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riskmesh.abstention import three_way_stats  # noqa: E402
from riskmesh.api import audit, bands, payloads  # noqa: E402
from riskmesh.api.artifacts import (  # noqa: E402
    Artifacts,
    ArtifactsNotFrozen,
    _FINGERPRINTED,
)

PASS = 0


def check(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ok   {msg}")


def test_01_artifacts_load_and_agree(a: Artifacts) -> None:
    from riskmesh.config import Config

    # Dynamic, not a literal: what actually matters is that the served
    # artifacts match the CURRENT code's config, not one specific historical
    # hash -- a hardcoded fingerprint has to be hand-updated on every
    # legitimate config change (a weight fold-back, a population raise) and
    # verifies nothing beyond artifacts.py's own cross-file agreement check.
    # Same treatment Task 3 gave the transaction-count check (cfg.target_txns
    # instead of a literal).
    assert a.fingerprint == Config().fingerprint(), (a.fingerprint, Config().fingerprint())
    # Deliberately a literal, not dynamic like the fingerprint check above: the
    # fingerprint pins config INPUTS, but a matching fingerprint says nothing
    # about component FORMATION (e.g. a graph.py union-find bug) -- this catches
    # a regression a config-fingerprint match cannot detect, so it stays pinned.
    assert len(a.components) == 336, len(a.components)
    check(f"01 artifacts load; all {len(_FINGERPRINTED)} fingerprinted files "
          f"agree with the current config ({a.fingerprint})")


def test_02_mixed_vintage_refuses() -> None:
    """A tampered fingerprint must fail the load, not warn."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = Path(__file__).resolve().parent.parent / "out"
        for f in src.iterdir():
            if f.is_file():
                (tmp / f.name).write_bytes(f.read_bytes())
        d = json.loads((tmp / "threshold.json").read_text())
        d["config_fingerprint"] = "deadbeefdeadbeef"
        (tmp / "threshold.json").write_text(json.dumps(d))
        try:
            Artifacts(tmp)
        except ArtifactsNotFrozen:
            check("02 mixed-vintage artifacts raise ArtifactsNotFrozen, not a warning")
            return
        raise AssertionError("a mismatched fingerprint was accepted")


def test_03_contribution_matches_frozen_score(a: Artifacts) -> None:
    """The API recomputes contribution; the sum must reproduce the frozen score."""
    worst = 0.0
    for comp in a.components:
        ev = payloads.evidence(a, comp["component_id"])
        assert ev is not None
        total = sum(s["contribution"] for s in ev["decomposition"]["signals"])
        worst = max(worst, abs(total - comp["score"]))
    # Exact, not approximate. If this ever loosens, the weights being used are
    # not the weights that scored the components -- weight_policy.json's copy is
    # rounded to 4dp and drifts by ~6e-5.
    assert worst < 1e-6, (
        f"contribution sum drifts from the frozen score by {worst:.2e}. "
        f"The API is not using the weights that produced components.csv."
    )
    check(f"03 contribution sum reproduces the frozen score EXACTLY for all "
          f"{len(a.components)} components (max drift {worst:.2e})")


def test_04_bands_agree_with_abstention(a: Artifacts) -> None:
    """The API's band logic must match the pipeline's, not merely resemble it."""
    from riskmesh.api.artifacts import ROOT
    sys.path.insert(0, str(ROOT))
    from riskmesh.config import Config
    from riskmesh.evaluate import build_candidates
    from riskmesh.generate import generate
    from riskmesh.graph import build_graph
    from riskmesh.score import score_all
    from riskmesh.split import assign_splits

    cfg = Config()
    txns, labels = generate(cfg)
    g = build_graph(cfg, txns)
    scores = score_all(cfg, txns, g)
    splits = assign_splits(cfg, g, labels)
    cands = build_candidates(cfg, g, scores, splits, labels)
    test = [c for c in cands if c.split == "test"]

    lo, hi = a.band["t_lo"], a.band["t_hi"]
    stats = three_way_stats(test, lo, hi, a.costs)
    mine = {"allow": 0, "review": 0, "escalate": 0}
    for c in test:
        mine[bands.action_for(c.score, lo, hi)] += 1
    assert mine["allow"] == stats["allow"], (mine, stats)
    assert mine["review"] == stats["review"], (mine, stats)
    assert mine["escalate"] == stats["escalate"], (mine, stats)
    check(f"04 bands.action_for agrees with abstention.three_way_stats "
          f"(allow {mine['allow']}, review {mine['review']}, escalate {mine['escalate']})")


def test_05_peer_rule_is_deterministic(a: Artifacts) -> None:
    test = a.in_split("test")
    flagged = [c for c in test if c["score"] >= a.band["t_lo"]]
    def peer_id(comp, pool) -> str:
        p = bands.select_peer(comp, pool)
        assert p is not None, f"no peer for {comp['component_id']}"
        return p["component_id"]

    baseline = {c["component_id"]: peer_id(c, test) for c in flagged}
    for _ in range(50):
        shuffled = test[:]
        random.shuffle(shuffled)
        for c in flagged:
            got = peer_id(c, shuffled)
            assert got == baseline[c["component_id"]], (c["component_id"], got)
    # No hardcoded component id here: the id space is a property of this
    # benchmark's generated data, not something this test should pin. The
    # loop above is the load-bearing check -- every flagged component's peer
    # is stable across 50 shuffles -- so a spot-check pair adds nothing a
    # specific id wouldn't also need updating on every legitimate re-freeze.
    check(f"05 peer rule stable over 50 shuffles for all {len(flagged)} flagged")


def test_06_payloads_carry_the_frozen_headline(a: Artifacts) -> None:
    """Payloads must reshape the frozen JSON on disk, not drift from it.

    No hardcoded headline numbers here: those move every time a protocol is
    honestly re-run (a weight fold-back, a new abstention band), and a
    literal would then need hand-updating for no extra safety -- what this
    test should catch is the reshaping itself going wrong, so it asserts
    payloads.* against a.json[...] (the frozen record straight off disk)
    instead.
    """
    ho = a.json["abstention_policy.json"]["held_out"]
    ev = a.json["eval_report.json"]["primary"]
    by = ho["by_action_and_label"]

    m = payloads.metrics(a)
    assert m["triage"] == {"allow": ho["actions"]["allow"],
                           "review": ho["actions"]["review"],
                           "escalate": ho["actions"]["escalate"],
                           "review_rate": ho["review_rate"],
                           "n_components": ho["n_components"]}, m["triage"]
    assert m["cost"]["expected_loss"] == ho["expected_loss"]
    assert m["cost"]["binary_baseline"] == ho["binary_baseline_same_rows"]["expected_loss"]
    assert m["quality"]["f1"] == ev["f1"]
    assert m["quality"]["escalated_false_positives"] == by["escalate_negative"]
    assert m["quality"]["rings_recovered"] == ev["rings_recovered"]

    t = payloads.threshold_analysis(a)
    ladder = {r["policy"]: r["expected_loss"] for r in t["ladder"]}
    costs = a.json["abstention_policy.json"]["costs"]
    positives, negatives = ev["tp"] + ev["fn"], ev["tn"] + ev["fp"]
    n = ho["n_components"]
    assert ladder["flag_nothing"] == round(positives * costs["false_negative"], 2), ladder
    assert ladder["flag_everything"] == round(
        negatives * costs["false_positive"] + n * costs["manual_review"], 2), ladder
    assert ladder["binary"] == ho["binary_baseline_same_rows"]["expected_loss"]
    assert ladder["three_way"] == ho["expected_loss"]

    b = payloads.benchmark(a)
    integ = a.json["integrity_report.json"]
    wp = a.json["weight_policy.json"]
    assert b["primary"]["f1"] == ev["f1"]
    assert b["panel"]["verdict"] == "PASS"
    assert (b["single_signal_max_f1"]["account_newness"]
            == integ["non_triviality"]["single_signal_max_f1"]["account_newness"])
    assert len(b["weight_search"]["candidates"]) == 5
    refused = [c for c in b["weight_search"]["candidates"] if not c["feasible"]]
    assert len(refused) == len(wp["infeasible"]), (refused, wp["infeasible"])
    check(f"06 metrics / threshold-analysis / benchmark carry the frozen headline "
          f"figures (three-way {ho['expected_loss']:,.2f} vs binary "
          f"{ho['binary_baseline_same_rows']['expected_loss']:,.2f}; "
          f"F1 {ev['f1']}; {by['escalate_negative']} escalated false positives; "
          f"{len(refused)} of 5 weight candidates refused)")


def test_07_evidence_matches_the_investigator_mockup(a: Artifacts) -> None:
    """No hardcoded component id or per-signal contribution values: those are
    properties of this benchmark's generated data and move on every honest
    re-freeze. What must hold regardless of the data is the structural
    contract -- zero-weighted signals kept and correctly attributed, action
    and rank agreeing with the same logic test_03/test_04 already verify
    generically, and a peer/graph actually served for the top-ranked
    component. Picks the highest-scoring test-split component dynamically
    (the old mockup's "rank 1" component) rather than a fixed id.
    """
    test = a.in_split("test")
    top = max(test, key=lambda c: c["score"])
    ev = payloads.evidence(a, top["component_id"])
    assert ev is not None

    ip = [s for s in ev["decomposition"]["signals"] if s["name"] == "ip_sharing"]
    assert len(ip) == 1, "ip_sharing must never be filtered out"
    assert ip[0]["weighted"] is False and ip[0]["note"] == "RISK-001"
    # instrument_sharing and merchant_concentration are also zeroed (folded
    # into Config()._default_weights() by a weight-search re-freeze), but by
    # RISK-004 and RISK-002 respectively, not by RISK-001 -- each zero-weighted
    # signal is mapped to the RISK item that actually zeroed it
    # (payloads.ZERO_WEIGHT_RISK_NOTES), not a single hardcoded label. All
    # three must still be served, never filtered out.
    assert next(s for s in ev["decomposition"]["signals"]
               if s["name"] == "instrument_sharing")["note"] == "RISK-004"
    assert next(s for s in ev["decomposition"]["signals"]
               if s["name"] == "merchant_concentration")["note"] == "RISK-002"

    assert ev["action"] == bands.action_for(top["score"], a.band["t_lo"], a.band["t_hi"])
    assert ev["rank"] == {"position": 1, "of": len(test)}, ev["rank"]
    expected_peer = bands.select_peer(top, test)
    if expected_peer is None:
        assert ev["comparison"] is None
    else:
        assert ev["comparison"]["peer"]["component_id"] == expected_peer["component_id"]
        assert ev["graph"]["accounts"] and ev["graph"]["edges"]
    check(f"07 /evidence for the top-ranked test component ({top['component_id']}, "
          f"action {ev['action']}): zero-weighted ip_sharing/instrument_sharing/"
          f"merchant_concentration kept with their own RISK-001/RISK-004/RISK-002 "
          f"notes, rank 1 of {len(test)}")


def test_08_audit_round_trip(a: Artifacts) -> None:
    """Two arbitrary, dynamically-picked component ids -- the audit log's
    correctness does not depend on which real components they are.
    """
    test = a.in_split("test")
    id_a, id_b = test[0]["component_id"], test[1]["component_id"]

    ev = payloads.evidence(a, id_a)
    assert ev is not None
    snapshot = {"signals": ev["decomposition"]["signals"], "summary": ev["summary"]}
    rec = audit.record(id_a, ev["action"], score=ev["score"], band=a.band,
                       system_action=ev["action"], fingerprint=a.fingerprint,
                       snapshot=snapshot)
    assert rec["agreed_with_system"] is True
    assert len(rec["evidence_sha256"]) == 64
    assert rec["evidence_snapshot"]["summary"]["size"] == ev["summary"]["size"]

    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "audit_log.jsonl"
        audit.append(rec, log)
        audit.append(audit.record(id_b, "allow", score=0.32, band=a.band,
                                  system_action="review", fingerprint=a.fingerprint,
                                  snapshot={}), log)
        log.write_text(log.read_text() + '{"torn": ', encoding="utf-8")
        back = audit.tail(path=log)
        assert len(back) == 2, back            # torn line skipped, history intact
        assert back[0]["component_id"] == id_b
        assert back[0]["agreed_with_system"] is False
        one = audit.tail(id_a, path=log)
        assert len(one) == 1 and one[0]["component_id"] == id_a
    try:
        audit.record(id_a, "delete-everything", score=0.5, band=a.band,
                     system_action="escalate", fingerprint=a.fingerprint, snapshot={})
    except ValueError:
        check("08 audit round-trips, skips a torn line, filters by component, "
              "and refuses an unknown action")
        return
    raise AssertionError("an invalid action was accepted")


def test_09_rings_listing(a: Artifacts) -> None:
    r = payloads.rings(a)
    test = a.in_split("test")
    assert r["total_in_split"] == len(test), r["total_in_split"]
    top = max(test, key=lambda c: c["score"])
    assert r["rings"][0]["component_id"] == top["component_id"]
    assert r["rings"][0]["rank"] == 1
    scores = [x["score"] for x in r["rings"]]
    assert scores == sorted(scores, reverse=True), "not ranked by score"

    ho = a.json["abstention_policy.json"]["held_out"]
    esc = payloads.rings(a, action="escalate")
    rev = payloads.rings(a, action="review")
    # Dynamic, not a literal: the band is non-degenerate this run (unlike
    # some prior runs), so Review is not necessarily empty -- both counts are
    # read from the frozen abstention record rather than assumed.
    assert esc["count"] == ho["actions"]["escalate"], (esc["count"], ho["actions"])
    assert rev["count"] == ho["actions"]["review"], (rev["count"], ho["actions"])
    assert all(x["action"] == "escalate" for x in esc["rings"])
    check(f"09 /rings ranks by score desc; action filter yields "
          f"{esc['count']} escalate, {rev['count']} review")


def test_10_task7_additions_served_verbatim(a: Artifacts) -> None:
    """Task 7: the API layer serves the seven-row baseline table (with the
    Tier 2 refusal row intact), the six-column threshold sweep, and the
    bootstrap CI -- reshaped, not recomputed or dropped.
    """
    b = payloads.benchmark(a)
    base_names = [row["baseline"] for row in b["baselines"]["baselines"]]
    assert base_names == ["random", "shared_device_only", "shared_ip_only",
                          "transaction_level", "ring_score",
                          "xgboost_scorer", "gnn_scorer"], base_names
    tier2 = next(r for r in b["baselines"]["baselines"] if r["baseline"] == "xgboost_scorer")
    assert tier2["feasible"] is False and tier2["held_out"] is None
    assert "refused" in tier2["status"]

    ci = b["bootstrap_ci"]
    assert ci == a.json["bootstrap_ci.json"], "benchmark() must serve bootstrap_ci verbatim"
    assert set(ci["metrics"]) == {"precision", "recall", "f1", "false_positive_rate"}

    t = payloads.threshold_analysis(a)
    sweep = t["sweep"]
    assert sweep["computed_on"] == "validation"
    assert len(sweep["grid"]) == 101
    six_cols = {"precision", "recall", "false_positive_count", "false_positive_rate",
                "false_negative_count", "false_negative_rate", "manual_reviews",
                "expected_loss"}
    assert all(six_cols <= set(row) for row in sweep["grid"])
    assert sum(1 for row in sweep["grid"] if row["selected"]) == 1
    # Ladder untouched by the sweep's addition.
    assert [r["policy"] for r in t["ladder"]] == \
        ["flag_nothing", "flag_everything", "binary", "three_way"]

    check(f"10 benchmark()/threshold-analysis serve the seven-row baseline "
          f"table (Tier 2 refused, Tier 3 present), the {len(sweep['grid'])}-row "
          f"threshold sweep with all six columns, and bootstrap_ci verbatim")


def main() -> None:
    print("\nriskmesh API -- data layer\n")
    a = Artifacts()
    test_01_artifacts_load_and_agree(a)
    test_02_mixed_vintage_refuses()
    test_03_contribution_matches_frozen_score(a)
    test_04_bands_agree_with_abstention(a)
    test_05_peer_rule_is_deterministic(a)
    test_06_payloads_carry_the_frozen_headline(a)
    test_07_evidence_matches_the_investigator_mockup(a)
    test_08_audit_round_trip(a)
    test_09_rings_listing(a)
    test_10_task7_additions_served_verbatim(a)
    print(f"\n{PASS}/{PASS} checks passed\n")


if __name__ == "__main__":
    main()
