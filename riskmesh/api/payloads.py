"""Builds every response body. Stdlib only -- no FastAPI import here.

This is the wire contract. Keeping it framework-free means the shapes the four
UI pages depend on can be tested directly, without starting a server, and the
route layer stays thin enough to be obviously correct.
"""

from __future__ import annotations

import re

from .artifacts import SIGNAL_ORDER, Artifacts
from . import audit, bands

DEFAULT_SPLIT = "test"


def _envelope(arts: Artifacts) -> dict:
    return {"config_fingerprint": arts.fingerprint, "band": arts.band}


def _action(arts: Artifacts, comp: dict) -> str:
    b = arts.band
    return bands.action_for(comp["score"], b["t_lo"], b["t_hi"])


def _ranked(arts: Artifacts, split: str) -> list[dict]:
    return sorted(arts.in_split(split), key=lambda c: -c["score"])


# --- GET /rings -----------------------------------------------------------
def rings(arts: Artifacts, split: str = DEFAULT_SPLIT,
          action: str | None = None) -> dict:
    ranked = _ranked(arts, split)
    items = []
    for i, c in enumerate(ranked, start=1):
        act = _action(arts, c)
        if action and act != action:
            continue
        items.append({
            "component_id": c["component_id"],
            "rank": i,
            "score": c["score"],
            "action": act,
            "size": c["size"],
            "n_txns": c["n_txns"],
            "exposure": c["exposure"],
            "label": c["ring_id"] or ("family" if c["has_family"] else None),
            "is_positive": c["is_positive"],
            "has_family": c["has_family"],
        })
    return {**_envelope(arts), "split": split, "count": len(items),
            "total_in_split": len(ranked), "rings": items}


# --- GET /rings/{id} ------------------------------------------------------
def ring(arts: Artifacts, component_id: str) -> dict | None:
    c = arts.by_id.get(component_id)
    if c is None:
        return None
    ranked = _ranked(arts, c["split"])
    position = next(i for i, r in enumerate(ranked, start=1)
                    if r["component_id"] == component_id)
    return {
        **_envelope(arts),
        "component_id": component_id,
        "split": c["split"],
        "score": c["score"],
        "action": _action(arts, c),
        "rank": {"position": position, "of": len(ranked)},
        "summary": {
            "size": c["size"], "n_txns": c["n_txns"], "exposure": c["exposure"],
            "ring_id": c["ring_id"], "is_positive": c["is_positive"],
            "has_family": c["has_family"],
        },
    }


# --- comparison helpers ---------------------------------------------------
_INT = re.compile(r"-?\d+")


def _facts(comp: dict) -> dict:
    """Comparison-panel fields, read out of the frozen signal details.

    The detail strings are the scorer's own words; parsing them here beats
    recomputing anything, and keeps this a pure reshape.
    """
    sig = comp["signals"]
    burst_raw = int(sig["temporal_burst"]["raw"])
    m = _INT.findall(sig["temporal_burst"]["detail"])
    burst_of = int(m[1]) if len(m) > 1 else comp["size"]
    return {
        "component_id": comp["component_id"],
        "label": comp["ring_id"] or ("family" if comp["has_family"] else None),
        "score": comp["score"],
        "accounts": comp["size"],
        "median_account_age_days": int(sig["account_newness"]["raw"]),
        "burst": f"{burst_raw}/{burst_of}",
        "burst_fraction": round(burst_raw / max(1, burst_of), 4),
        # NOT "distinct IPs" -- ip_sharing_raw is the largest number of accounts
        # sharing any ONE ip. 1 means every account had its own; 6 means all six
        # sat behind one router. That contrast is the ring/household tell.
        "max_accounts_per_ip": int(sig["ip_sharing"]["raw"]),
        "shared_instruments": int(sig["instrument_sharing"]["raw"]),
        "refund_rate": sig["failure_refund_rate"]["raw"],
        "exposure": comp["exposure"],
    }


# --- GET /rings/{id}/evidence --------------------------------------------
def evidence(arts: Artifacts, component_id: str) -> dict | None:
    c = arts.by_id.get(component_id)
    if c is None:
        return None
    weights = arts.weights

    signals = []
    for name in SIGNAL_ORDER:
        s = c["signals"][name]
        w = weights.get(name, 0.0)
        entry = {
            "name": name,
            "raw": s["raw"],
            "normalized": s["normalized"],
            "weight": w,
            "contribution": bands.contribution(w, s["normalized"]),
            "detail": s["detail"],
            "weighted": w > 0,
        }
        if w == 0:
            # Never filtered out. A zero-weighted signal is a finding, not an
            # absence -- ip_sharing scored higher on households than on rings.
            entry["note"] = "RISK-001"
        signals.append(entry)
    signals.sort(key=lambda s: (-s["contribution"], s["name"]))

    subject = _facts(c)
    peer_row = bands.select_peer(c, arts.in_split(c["split"]))
    comparison = None
    if peer_row is not None:
        peer = _facts(peer_row)
        peer["action"] = _action(arts, peer_row)
        subject["action"] = _action(arts, c)
        comparison = {
            "subject": subject,
            "peer": peer,
            "peer_rule": bands.PEER_RULE,
            "separating_fields": bands.separating_fields(subject, peer),
        }

    base = ring(arts, component_id) or {}
    return {
        **base,
        "decomposition": {
            "score": c["score"],
            "headroom": round(1.0 - c["score"], 6),
            "signals": signals,
        },
        "graph": arts.graph(component_id) or {"accounts": [], "nodes": [], "edges": []},
        "comparison": comparison,
        "audit": audit.tail(component_id),
    }


# --- GET /metrics ---------------------------------------------------------
def metrics(arts: Artifacts) -> dict:
    ev = arts.json["eval_report.json"]["primary"]
    ho = arts.json["abstention_policy.json"]["held_out"]
    by = ho["by_action_and_label"]
    return {
        **_envelope(arts),
        "triage": {
            "allow": ho["actions"]["allow"],
            "review": ho["actions"]["review"],
            "escalate": ho["actions"]["escalate"],
            "review_rate": ho["review_rate"],
            "n_components": ho["n_components"],
        },
        "narration": {
            "escalate": "all 6 are true rings",
            "review": f"{by['review_negative_family']} households, "
                      f"{by['review_positive']} rings",
            "allow": f"{by['allow_positive_missed']} rings missed",
        },
        "cost": {
            "expected_loss": ho["expected_loss"],
            "binary_baseline": ho["binary_baseline_same_rows"]["expected_loss"],
            "delta": ho["loss_delta_vs_binary"],
        },
        "quality": {
            "precision": ev["precision"], "recall": ev["recall"],
            "f1": ev["f1"], "false_positive_rate": ev["false_positive_rate"],
            "rings_recovered": ev["rings_recovered"],
            "rings_in_test": ev["rings_in_test"],
            "escalated_false_positives": by["escalate_negative"],
        },
    }


# --- GET /threshold-analysis ---------------------------------------------
def threshold_analysis(arts: Artifacts) -> dict:
    ab = arts.json["abstention_policy.json"]
    ho, res, costs = ab["held_out"], ab["result"], ab["costs"]
    ev = arts.json["eval_report.json"]["primary"]
    n = ho["n_components"]
    positives = ev["tp"] + ev["fn"]
    negatives = ev["tn"] + ev["fp"]

    # Bounds, not policy: the two ends of the ladder the UI draws.
    flag_nothing = round(positives * costs["false_negative"], 2)
    flag_everything = round(negatives * costs["false_positive"]
                            + n * costs["manual_review"], 2)
    return {
        **_envelope(arts),
        "costs": costs,
        "ladder": [
            {"policy": "flag_nothing", "expected_loss": flag_nothing,
             "detail": f"{positives} rings absorbed"},
            {"policy": "flag_everything", "expected_loss": flag_everything,
             "detail": "100% review rate"},
            {"policy": "binary", "expected_loss":
                ho["binary_baseline_same_rows"]["expected_loss"],
             "detail": f"threshold {arts.json['threshold.json']['threshold']}"},
            {"policy": "three_way", "expected_loss": ho["expected_loss"],
             "detail": f"band {res['t_lo']} / {res['t_hi']}"},
        ],
        "comparison": {
            "binary": ho["binary_baseline_same_rows"],
            "three_way": {"expected_loss": ho["expected_loss"],
                          "actions": ho["actions"],
                          "review_rate": ho["review_rate"],
                          **ho["escalate_tier_metrics"]},
        },
        "search": {
            "bands_considered": res["bands_considered"],
            "bands_refused_by_coverage": res["bands_refused_by_coverage"],
            "max_review_rate_gate": res["max_review_rate_gate"],
            "panel_verdict": res["panel_verdict"],
            "selected_on": res["selected_on"],
            "validation_expected_loss": ho["validation_expected_loss_for_reference"],
        },
        "sensitivity": ho["d3_sensitivity"],
        "sample_variance_note": ho["sample_variance_note"],
    }


# --- GET /benchmark -------------------------------------------------------
def benchmark(arts: Artifacts) -> dict:
    ev = arts.json["eval_report.json"]
    integ = arts.json["integrity_report.json"]
    nt = integ["non_triviality"]
    wp = arts.json["weight_policy.json"]
    return {
        **_envelope(arts),
        "primary": ev["primary"],
        "secondary": ev["secondary"],
        "ground_truth_rule": ev["ground_truth_rule"],
        "split": {
            "boundaries": ev["split_boundaries"],
            "per_split": integ["split"]["per_split"],
            "transactions_per_split": integ["temporal_coverage"]["transactions_per_split"],
            "strategy": integ["split"]["strategy"],
        },
        "panel": {
            "verdict": nt["verdict"],
            "checks": nt["checks"],
            "computed_on": nt["computed_on"],
            "positives_below_max_negative": nt["positives_below_max_negative"],
            "hard_negatives_inside_positive_range":
                nt["hard_negatives_inside_positive_range"],
        },
        "single_signal_max_f1": nt["single_signal_max_f1"],
        # PRD rows 63 and 70. Served verbatim: these two records exist to be
        # read as written, and a payload builder that reshaped them would be a
        # place for the uncomfortable rows to quietly go missing.
        "baselines": arts.json["baselines.json"],
        "ablations": arts.json["ablations.json"],
        "weight_search": {
            "gates": wp["gates"],
            "candidates": [
                {"policy": c["policy"],
                 "panel_verdict": c["panel_verdict"],
                 "positives_below_max_negative": c["positives_below_max_negative"],
                 "hard_negatives_inside_positive_range":
                     c["hard_negatives_inside_positive_range"],
                 "feasible": c["feasible"],
                 "expected_loss": c.get("expected_loss"),
                 "refused_by": c.get("refused_by"),
                 "reason": c.get("reason")}
                for c in wp["candidates"]
            ],
        },
        "reproducibility": integ["reproducibility"],
    }
