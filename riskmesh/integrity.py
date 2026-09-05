"""Data-integrity report: is this benchmark worth believing?

Everything the PRD's "Data Integrity Checks" section asks for, plus the piece
that matters most for a hackathon judge -- the **non-triviality panel**.

A synthetic fraud benchmark fails in a specific way: the generator makes abuse
so distinct from normal that any rule separates them, every metric reads 1.00,
and the numbers mean nothing. The panel measures exactly that, prints each
number next to the bound it must satisfy, and marks it PASS / FLAG / FAIL. A
benchmark that has drifted into being too easy is then visible in the report
itself rather than only in a failing test.

**The panel is computed on train + validation components only.** These are the
numbers you would tune the generator against, and the PRD forbids using test
statistics to tune generator parameters. Test distributions are described after
the fact in `eval_report.json`, never fed back.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter
from typing import Any

from .config import SIGNALS, Config
from .evaluate import (
    GROUND_TRUTH_RULE,
    Candidate,
    shared_device_baseline_f1,
    single_signal_detail,
)
from .generate import Label, Txn, accounts_per_attribute
from .graph import Graph
from .split import SplitResult, split_report

MINUTES_PER_DAY = 24 * 60


def _hist(counts: dict[str, int]) -> dict[str, int]:
    """value -> how many attribute nodes had that many distinct accounts."""
    return {str(k): v for k, v in sorted(Counter(counts.values()).items())}


def _spread(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "sd": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "sd": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _overlap(pos: list[float], neg: list[float]) -> dict[str, Any]:
    """Do the two score distributions actually intersect?"""
    if not pos or not neg:
        return {"overlaps": False, "reason": "one class is empty"}
    lo = max(min(pos), min(neg))
    hi = min(max(pos), max(neg))
    return {
        "positive_range": [round(min(pos), 4), round(max(pos), 4)],
        "negative_range": [round(min(neg), 4), round(max(neg), 4)],
        "intersection": [round(lo, 4), round(hi, 4)] if lo <= hi else None,
        "overlaps": lo <= hi,
        "width": round(hi - lo, 4) if lo <= hi else 0.0,
    }


def non_triviality_panel(cfg: Config, candidates: list[Candidate]) -> dict[str, Any]:
    """The honesty check. Train+validation only -- never test."""
    fit = [c for c in candidates if c.split in ("train", "validation")]
    pos = [c for c in fit if c.is_positive]
    neg = [c for c in fit if not c.is_positive]
    pos_scores = [c.score for c in pos]
    neg_scores = [c.score for c in neg]

    overlap = _overlap(pos_scores, neg_scores)
    max_neg = max(neg_scores) if neg_scores else 0.0
    below = sum(1 for s in pos_scores if s < max_neg)
    frac_below = below / len(pos_scores) if pos_scores else 0.0

    family_neg = [c.score for c in neg if c.has_family]
    min_pos = min(pos_scores) if pos_scores else 1.0
    families_in_pos_range = [s for s in family_neg if s >= min_pos]

    detail = single_signal_detail(fit)
    per_signal = {k: d["f1"] for k, d in detail.items()}
    perfect = sorted(k for k, v in per_signal.items() if v >= 1.0)
    flagged = sorted(
        k for k, v in per_signal.items() if cfg.single_signal_flag_f1 <= v < 1.0
    )
    inverted = sorted(k for k, d in detail.items() if d["direction"] == "<=")
    device_f1 = shared_device_baseline_f1(fit)

    # Sign check on the NORMALISED values -- the numbers that actually enter the
    # weighted score. A raw "<=" direction is not itself a fault: account_newness
    # inverts during normalisation by design, so its raw direction is "<=" while
    # its contribution is strongly correct. Only this table can tell the two
    # apart, and mis-signing one weighted signal is what RISK-001 was.
    #
    # signal_sign_check vs. no_weighted_signal_mis_signed -- complementary, not
    # contradictory. sign_check below is a DIAGNOSTIC computed over every signal
    # in SIGNALS, including zero-weighted ones (ip_sharing, RISK-001): it exists
    # so a signal can be watched even before it earns weight. The gate,
    # `no_weighted_signal_mis_signed` in `checks` below, filters that same table
    # to `weight > 0` only -- a zero-weighted signal reading MIS-SIGNED (as
    # ip_sharing does, by design: RISK-001) cannot fail it, because it makes no
    # contribution to the score. Reading ip_sharing's row as a contradiction of
    # the gate's PASS is the mistake this comment exists to prevent.
    sign_check: dict[str, Any] = {}
    for name in SIGNALS:
        mean_pos = statistics.fmean([c.signals[name] for c in pos]) if pos else 0.0
        mean_neg = statistics.fmean([c.signals[name] for c in neg]) if neg else 0.0
        delta = mean_pos - mean_neg
        weight = cfg.weights[name]
        if delta < -cfg.mis_signed_delta_tolerance:
            status = "MIS-SIGNED"
        elif delta > cfg.mis_signed_delta_tolerance:
            status = "ok"
        else:
            status = "no separation"
        sign_check[name] = {
            "weight": round(weight, 4),
            "normalised_mean_positive": round(mean_pos, 4),
            "normalised_mean_negative": round(mean_neg, 4),
            "delta": round(delta, 4),
            "weighted_contribution": round(weight * delta, 4),
            "status": status,
        }
    mis_signed = sorted(
        k for k, v in sign_check.items()
        if v["status"] == "MIS-SIGNED" and v["weight"] > 0
    )
    total_separation = round(
        sum(v["weighted_contribution"] for v in sign_check.values()), 4
    )

    checks = {
        "score_distributions_overlap": {
            "value": overlap["overlaps"], "bound": True,
            "status": "PASS" if overlap["overlaps"] else "FAIL",
        },
        "positives_below_max_negative": {
            "value": round(frac_below, 4),
            "bound": f">= {cfg.min_positive_below_max_negative_fraction}",
            "status": "PASS" if frac_below >= cfg.min_positive_below_max_negative_fraction
            else "FAIL",
        },
        "hard_negative_in_positive_range": {
            "value": len(families_in_pos_range), "bound": ">= 1",
            "status": "PASS" if families_in_pos_range else "FAIL",
        },
        "no_single_signal_separates_perfectly": {
            "value": perfect or None, "bound": "no signal with F1 == 1.0",
            "status": "FAIL" if perfect else "PASS",
        },
        "shared_device_baseline_not_near_perfect": {
            "value": device_f1, "bound": f"< {cfg.max_shared_device_baseline_f1}",
            "status": "PASS" if device_f1 < cfg.max_shared_device_baseline_f1 else "FAIL",
        },
        # FLAG, not FAIL. A mis-signed weighted signal is a real defect, but
        # deciding what to do about it is a judgement call that belongs to
        # feature validation, not to a gate that blocks the benchmark running.
        "no_weighted_signal_mis_signed": {
            "value": mis_signed or None, "bound": "no weighted signal helps negatives",
            "status": "FLAG" if mis_signed else "PASS",
        },
    }

    return {
        "computed_on": "train+validation only (test statistics never tune the generator)",
        "n_positive": len(pos), "n_negative": len(neg),
        "score_overlap": overlap,
        "max_negative_score": round(max_neg, 4),
        "min_positive_score": round(min_pos, 4),
        "positives_below_max_negative": {"count": below, "fraction": round(frac_below, 4)},
        "hard_negative_scores": _spread(family_neg),
        "hard_negatives_inside_positive_range": len(families_in_pos_range),
        "single_signal_max_f1": per_signal,
        "single_signal_detail": detail,
        "signal_sign_check": sign_check,
        "signal_sign_check_note": (
            "A diagnostic over every signal, including zero-weighted ones -- "
            "ip_sharing reads MIS-SIGNED here by design (RISK-001) and that is "
            "expected, not a contradiction of the PASS below. The "
            "no_weighted_signal_mis_signed check/FLAG filters this same table "
            "to weight > 0 only, because a zero-weighted signal contributes "
            "nothing to the score regardless of its sign."
        ),
        "mis_signed_weighted_signals": mis_signed,
        "total_weighted_score_separation": total_separation,
        "inverted_signals": inverted,
        "inverted_signals_note": (
            "RAW-value direction only. A <= direction is not by itself a fault: "
            "account_newness inverts during normalisation by design. Use "
            "signal_sign_check, which is computed on the normalised values that "
            "actually enter the score, to tell a correct inversion from a "
            "mis-signed one."
        ),
        "flagged_signals": {
            k: per_signal[k] for k in flagged
        } or "none -- no signal in [%.2f, 1.0)" % cfg.single_signal_flag_f1,
        "flagged_signals_note": (
            "A signal in [%.2f, 1.0) is strong but not disqualifying -- investigate "
            "it by hand. Only perfect separation (F1 == 1.0) fails the run."
            % cfg.single_signal_flag_f1
        ),
        "shared_device_only_baseline_f1": device_f1,
        "per_signal_raw": {
            name: {
                "positive": _spread([c.raw_signals[name] for c in pos]),
                "negative": _spread([c.raw_signals[name] for c in neg]),
            }
            for name in SIGNALS
        },
        "checks": checks,
        "verdict": "FAIL" if any(v["status"] == "FAIL" for v in checks.values())
        else "PASS",
    }


def integrity_report(
    cfg: Config, txns: list[Txn], labels: list[Label], graph: Graph,
    splits: SplitResult, candidates: list[Candidate],
) -> dict[str, Any]:
    accounts = {t.account_id for t in txns}
    per_device = accounts_per_attribute(txns, "device_id")
    per_ip = accounts_per_attribute(txns, "ip_id")
    per_instrument = accounts_per_attribute(txns, "instrument_id")

    sizes = [c.size for c in graph.components]
    largest = max(sizes, default=0)

    ring_sizes = Counter(lb.ring_id for lb in labels if lb.ring_id)
    family_sizes = Counter(lb.cluster_id for lb in labels if lb.cluster_id)

    # Task 3: which of the five mechanisms each ring is, and where it landed.
    # One ring_type/active_period per ring (every member of a ring agrees --
    # split.py's own ring-level guarantee), so reading either off any one
    # member's label is exact, not a majority vote.
    ring_type_by_ring = {lb.ring_id: lb.ring_type for lb in labels if lb.ring_id}
    ring_period_by_ring = {lb.ring_id: lb.active_period for lb in labels if lb.ring_id}
    ring_type_counts = Counter(ring_type_by_ring.values())
    ring_type_by_split: dict[str, Counter] = {name: Counter() for name in cfg.split_boundaries}
    for rid, rtype in ring_type_by_ring.items():
        ring_type_by_split[ring_period_by_ring[rid]][rtype] += 1

    # Task 4: which of the four hard-negative mechanisms each cluster is, and
    # where it landed -- same one-per-cluster exactness as rings above (every
    # member of a cluster agrees, split.py's own cluster-level guarantee).
    cluster_type_by_cluster = {lb.cluster_id: lb.cluster_type for lb in labels if lb.cluster_id}
    cluster_period_by_cluster = {
        lb.cluster_id: lb.active_period for lb in labels if lb.cluster_id
    }
    cluster_type_counts = Counter(cluster_type_by_cluster.values())
    cluster_type_by_split: dict[str, Counter] = {
        name: Counter() for name in cfg.split_boundaries
    }
    for cid, ctype in cluster_type_by_cluster.items():
        cluster_type_by_split[cluster_period_by_cluster[cid]][ctype] += 1

    days = [t.ts_minute // MINUTES_PER_DAY for t in txns]
    per_split_class: dict[str, dict[str, int]] = {}
    for name in cfg.split_boundaries:
        members = [c for c in candidates if c.split == name]
        per_split_class[name] = {
            "components": len(members),
            "positive": sum(1 for c in members if c.is_positive),
            "negative": sum(1 for c in members if not c.is_positive),
            "with_family_cluster": sum(1 for c in members if c.has_family),
            "unlabelled": sum(
                1 for c in members if not c.is_positive and not c.has_family
            ),
        }

    return {
        "reproducibility": {
            "seed": cfg.seed,
            "config_fingerprint": cfg.fingerprint(),
            "python_version": sys.version.split()[0],
            "note": "CPython guarantees random() across versions, not shuffle/"
                    "sample/gauss -- byte-identical output is claimed within one "
                    "interpreter version only",
        },
        "ground_truth_rule": GROUND_TRUTH_RULE,
        "entities": {
            "transactions": len(txns),
            "accounts": len(accounts),
            "accounts_with_labels": sum(
                1 for lb in labels if lb.ring_id or lb.cluster_id
            ),
            "devices": len(per_device),
            "ips": len(per_ip),
            "instruments": len(per_instrument),
            "merchants": len({t.merchant_id for t in txns}),
        },
        "reuse_distributions": {
            "accounts_per_device": _hist(per_device),
            "accounts_per_ip": _hist(per_ip),
            "accounts_per_instrument": _hist(per_instrument),
        },
        "component_hygiene": {
            "candidate_components": len(graph.components),
            "singletons_dropped": graph.dropped_singletons,
            "size_distribution": {str(k): v for k, v in sorted(Counter(sizes).items())},
            "largest_component_accounts": largest,
            "largest_component_share": round(largest / max(1, len(accounts)), 4),
            "largest_component_bound": cfg.max_largest_component_share,
            "giant_components": sum(
                1 for s in sizes if s > cfg.max_largest_component_share * len(accounts)
            ),
            "capped_nodes": {k: len(v) for k, v in graph.capped.items()},
            "capped_examples": {
                k: sorted(v)[:3] for k, v in graph.capped.items() if v
            },
            "rules": [
                "merchants never link (everyone touches the popular ones)",
                f"degree cap: ip>{cfg.max_ip_degree}, device>{cfg.max_device_degree}, "
                f"instrument>{cfg.max_instrument_degree} accounts = common infrastructure",
                f"minimum edge weight: {cfg.min_edge_txns} transactions to link",
            ],
        },
        "injected": {
            "rings": len(ring_sizes),
            "ring_size_distribution": {
                str(k): v for k, v in sorted(Counter(ring_sizes.values()).items())
            },
            "ring_type_distribution": dict(sorted(ring_type_counts.items())),
            "ring_type_by_split": {
                name: dict(sorted(c.items())) for name, c in ring_type_by_split.items()
            },
            "family_clusters": len(family_sizes),
            "family_size_distribution": {
                str(k): v for k, v in sorted(Counter(family_sizes.values()).items())
            },
            "cluster_type_distribution": dict(sorted(cluster_type_counts.items())),
            "cluster_type_by_split": {
                name: dict(sorted(c.items())) for name, c in cluster_type_by_split.items()
            },
        },
        "temporal_coverage": {
            "days": [min(days, default=0), max(days, default=0)],
            "transactions_per_split": {
                name: sum(1 for d in days if lo <= d < hi)
                for name, (lo, hi) in cfg.split_boundaries.items()
            },
        },
        "split": split_report(cfg, splits),
        "class_balance": per_split_class,
        "non_triviality": non_triviality_panel(cfg, candidates),
    }


def print_report(report: dict[str, Any]) -> None:
    """Terminal summary. The JSON file is the record; this is the read-at-a-glance."""
    e, h, p = report["entities"], report["component_hygiene"], report["non_triviality"]
    r = report["reproducibility"]

    print("=" * 72)
    print("RiskMesh Tier 0 - data integrity report")
    print("=" * 72)
    print(f"seed {r['seed']}   config {r['config_fingerprint']}   python {r['python_version']}")
    print(f"\n{e['transactions']} transactions, {e['accounts']} accounts, "
          f"{e['devices']} devices, {e['ips']} IPs, {e['merchants']} merchants")
    print(f"{report['injected']['rings']} rings, "
          f"{report['injected']['family_clusters']} family clusters injected")
    print(f"ring types: {report['injected']['ring_type_distribution']}")
    print(f"cluster types: {report['injected']['cluster_type_distribution']}")

    print(f"\ncomponents: {h['candidate_components']} candidates, "
          f"{h['singletons_dropped']} singletons dropped")
    print(f"largest component: {h['largest_component_accounts']} accounts "
          f"({h['largest_component_share']:.1%}, bound {h['largest_component_bound']:.0%})")
    print("capped as common infrastructure: " +
          ", ".join(f"{k}={v}" for k, v in h["capped_nodes"].items()))

    print("\nclass balance by split:")
    for name, stats in report["class_balance"].items():
        print(f"  {name:11s} {stats['components']:3d} components  "
              f"{stats['positive']:2d} positive  {stats['negative']:3d} negative  "
              f"({stats['with_family_cluster']} with a family cluster)")

    print(f"\nnon-triviality panel  [{p['computed_on']}]")
    for name, chk in p["checks"].items():
        mark = {"PASS": "ok  ", "FLAG": "FLAG", "FAIL": "FAIL"}[chk["status"]]
        print(f"  [{mark}] {name:42s} {str(chk['value']):>10s}  bound {chk['bound']}")
    if isinstance(p["flagged_signals"], dict) and p["flagged_signals"]:
        print(f"  note: signals to investigate by hand -> {p['flagged_signals']}")
    if p["mis_signed_weighted_signals"]:
        print(f"  note: weighted signals contributing the WRONG way -> "
              f"{p['mis_signed_weighted_signals']}")
    print(f"  total weighted score separation (positive - negative): "
          f"{p['total_weighted_score_separation']:+.4f}")
    print(f"  positive scores {p['score_overlap']['positive_range']}   "
          f"negative scores {p['score_overlap']['negative_range']}   "
          f"overlap {p['score_overlap']['intersection']}")
    print(f"\n  VERDICT: {p['verdict']}")
    print("=" * 72)
