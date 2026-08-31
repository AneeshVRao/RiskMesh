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
from riskmesh.api.artifacts import Artifacts, ArtifactsNotFrozen  # noqa: E402

PASS = 0


def check(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ok   {msg}")


def test_01_artifacts_load_and_agree(a: Artifacts) -> None:
    assert a.fingerprint == "c3ee14627c2c2ce2", a.fingerprint
    assert len(a.components) == 105, len(a.components)
    assert a.band == {"t_lo": 0.14, "t_hi": 0.23}, a.band
    check(f"01 artifacts load; all 5 fingerprinted files agree ({a.fingerprint})")


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
    assert baseline["c_a00653"] == "c_a00744", baseline["c_a00653"]
    check(f"05 peer rule stable over 50 shuffles for all {len(flagged)} flagged; "
          f"c_a00653 -> c_a00744")


def test_06_payloads_carry_the_frozen_headline(a: Artifacts) -> None:
    m = payloads.metrics(a)
    assert m["triage"] == {"allow": 19, "review": 5, "escalate": 8,
                           "review_rate": 0.1562, "n_components": 32}, m["triage"]
    assert m["cost"]["expected_loss"] == 6808.33
    assert m["cost"]["binary_baseline"] == 8041.65
    assert m["quality"]["f1"] == 0.875
    assert m["quality"]["escalated_false_positives"] == 1
    assert m["quality"]["rings_recovered"] == 7

    t = payloads.threshold_analysis(a)
    ladder = {r["policy"]: r["expected_loss"] for r in t["ladder"]}
    assert ladder["flag_nothing"] == 615887.28, ladder
    assert ladder["flag_everything"] == 23399.92, ladder
    assert ladder["binary"] == 8041.65 and ladder["three_way"] == 6808.33, ladder

    b = payloads.benchmark(a)
    assert b["primary"]["f1"] == 0.875
    assert b["panel"]["verdict"] == "PASS"
    assert b["single_signal_max_f1"]["account_newness"] == 0.5833
    assert len(b["weight_search"]["candidates"]) == 5
    refused = [c for c in b["weight_search"]["candidates"] if not c["feasible"]]
    assert len(refused) == 2, refused
    check("06 metrics / threshold-analysis / benchmark carry the frozen headline "
          "figures (6,808.33 vs 8,041.65; F1 0.8750; 1 false escalation; 2 refused)")


def test_07_evidence_matches_the_investigator_mockup(a: Artifacts) -> None:
    ev = payloads.evidence(a, "c_a00653")
    assert ev is not None
    got = {s["name"]: s["contribution"] for s in ev["decomposition"]["signals"]}
    for name, want in (("device_sharing", 0.17284), ("temporal_burst", 0.192901),
                       ("account_newness", 0.110425),
                       ("failure_refund_rate", 0.113858),
                       ("instrument_pool_concentration", 0.0),
                       ("instrument_sharing", 0.0),
                       ("merchant_concentration", 0.0)):
        assert abs(got[name] - want) < 5e-5, (name, got[name], want)
    # The ring keeps one account per IP; the household puts several behind one
    # router. That inversion is the comparison panel's whole argument.
    assert ev["comparison"]["subject"]["max_accounts_per_ip"] == 1
    assert ev["comparison"]["peer"]["max_accounts_per_ip"] == 7

    ip = [s for s in ev["decomposition"]["signals"] if s["name"] == "ip_sharing"]
    assert len(ip) == 1, "ip_sharing must never be filtered out"
    assert ip[0]["weighted"] is False and ip[0]["note"] == "RISK-001"
    # Phase 11: the weight search re-run zeroed instrument_sharing and
    # merchant_concentration too (D_drop_flagged won) -- both must still be
    # served, never filtered out, same as ip_sharing.
    for name in ("instrument_sharing", "merchant_concentration"):
        sig = next(s for s in ev["decomposition"]["signals"] if s["name"] == name)
        assert sig["weighted"] is False and sig["note"] == "RISK-001"

    assert ev["action"] == "escalate"
    assert ev["rank"] == {"position": 1, "of": 32}
    assert ev["comparison"]["peer"]["component_id"] == "c_a00744"
    assert ev["graph"]["accounts"] and ev["graph"]["edges"]
    check("07 /evidence reproduces the Investigator mockup: contributions, "
          "zero-weighted ip_sharing/instrument_sharing/merchant_concentration "
          "kept with RISK-001, rank 1 of 32")


def test_08_audit_round_trip(a: Artifacts) -> None:
    ev = payloads.evidence(a, "c_a00653")
    assert ev is not None
    snapshot = {"signals": ev["decomposition"]["signals"], "summary": ev["summary"]}
    rec = audit.record("c_a00653", "escalate", score=ev["score"], band=a.band,
                       system_action=ev["action"], fingerprint=a.fingerprint,
                       snapshot=snapshot)
    assert rec["agreed_with_system"] is True
    assert len(rec["evidence_sha256"]) == 64
    assert rec["evidence_snapshot"]["summary"]["size"] == 8

    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "audit_log.jsonl"
        audit.append(rec, log)
        audit.append(audit.record("c_a00744", "allow", score=0.32, band=a.band,
                                  system_action="review", fingerprint=a.fingerprint,
                                  snapshot={}), log)
        log.write_text(log.read_text() + '{"torn": ', encoding="utf-8")
        back = audit.tail(path=log)
        assert len(back) == 2, back            # torn line skipped, history intact
        assert back[0]["component_id"] == "c_a00744"
        assert back[0]["agreed_with_system"] is False
        one = audit.tail("c_a00653", path=log)
        assert len(one) == 1 and one[0]["component_id"] == "c_a00653"
    try:
        audit.record("c_a00653", "delete-everything", score=0.5, band=a.band,
                     system_action="escalate", fingerprint=a.fingerprint, snapshot={})
    except ValueError:
        check("08 audit round-trips, skips a torn line, filters by component, "
              "and refuses an unknown action")
        return
    raise AssertionError("an invalid action was accepted")


def test_09_rings_listing(a: Artifacts) -> None:
    r = payloads.rings(a)
    assert r["total_in_split"] == 32, r["total_in_split"]
    assert r["rings"][0]["component_id"] == "c_a00653"
    assert r["rings"][0]["rank"] == 1
    scores = [x["score"] for x in r["rings"]]
    assert scores == sorted(scores, reverse=True), "not ranked by score"
    esc = payloads.rings(a, action="escalate")
    rev = payloads.rings(a, action="review")
    assert esc["count"] == 8 and rev["count"] == 5, (esc["count"], rev["count"])
    assert all(x["action"] == "escalate" for x in esc["rings"])
    check("09 /rings ranks by score desc; action filter yields 8 escalate, 5 review")


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
    print(f"\n{PASS}/{PASS} checks passed\n")


if __name__ == "__main__":
    main()
