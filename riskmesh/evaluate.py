"""Leakage-safe evaluation: ground-truth labelling, threshold freeze, metrics.

The protocol this module enforces is the point of Tier 0:

1. `select_threshold()` sees **validation candidates only**. Its signature makes
   it impossible to hand it the test split.
2. The chosen value is written to `out/threshold.json` *before any test data is
   read*, so the freeze is auditable after the fact rather than merely claimed.
3. `evaluate()` takes a threshold as an argument. The runner reads it back from
   the frozen file rather than recomputing it.

Metrics are reported at two units. Component-level is primary: a component is
what an analyst actually reviews, and it is what the PRD asks the risk score to
cover. Account-level is secondary, with each account inheriting its component's
score -- useful because the denominators are larger, misleading on its own
because one wrong big component costs as many false positives as it has members.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import SIGNALS, Config
from .generate import Label
from .graph import Graph
from .score import ComponentScore
from .split import SplitResult

# --------------------------------------------------------------------------
# Tier 0 benchmark ground-truth rule
# --------------------------------------------------------------------------
#
# A component counts as positive iff at least `positive_component_ring_fraction`
# of its accounts belong to a SINGLE injected ring.
#
# This is a labelling convention *for this benchmark*, not a definition of what a
# risk ring is. Ring topologies exist that it will not capture: a chain of
# pairwise-shared attributes can spread one ring across a large component in
# which no single ring holds a majority, and this rule would score that component
# negative. That is a known Tier 0 scope limit, not a bug -- Tier 0 injects only
# compact shared-device rings, for which the rule is well behaved. Anything
# relying on a different topology needs a different rule.
GROUND_TRUTH_RULE = (
    "Tier 0 benchmark ground-truth rule: a component is positive iff >=50% of "
    "its accounts belong to a single injected ring. A labelling convention for "
    "this benchmark, not a definition of a risk ring; chain-topology rings where "
    "no single ring holds a majority are a known Tier 0 scope limit."
)


@dataclass
class Candidate:
    """One scored component, its split, and its ground truth -- kept apart.

    `score` is computed with no access to labels; `is_positive` is read from the
    label file. They meet here, in the evaluator, and nowhere earlier.
    """

    component_id: str
    split: str
    score: float
    signals: dict[str, float]  # normalised value per signal, for ablation/baselines
    raw_signals: dict[str, float]
    accounts: set[str]
    is_positive: bool
    ring_id: str  # the majority ring, when positive
    has_family: bool
    cluster_id: str  # the majority hard-negative cluster, "" if none (audit
                      # finding #16: has_family alone cannot tell test_03
                      # WHICH cluster a component belongs to, so it could not
                      # check split isolation for clusters the way it does
                      # for rings via ring_id)
    n_txns: int
    exposure: float


def build_candidates(
    cfg: Config, graph: Graph, scores: list[ComponentScore],
    splits: SplitResult, labels: list[Label],
) -> list[Candidate]:
    by_account = {lb.account_id: lb for lb in labels}
    comps = {c.component_id: c for c in graph.components}
    out: list[Candidate] = []

    for s in scores:
        comp = comps[s.component_id]
        ring_counts: dict[str, int] = defaultdict(int)
        cluster_counts: dict[str, int] = defaultdict(int)
        has_family = False
        for a in comp.accounts:
            lb = by_account[a]
            if lb.ring_id:
                ring_counts[lb.ring_id] += 1
            if lb.cluster_id:
                has_family = True
                cluster_counts[lb.cluster_id] += 1

        ring_id, n_members = "", 0
        if ring_counts:
            ring_id, n_members = max(ring_counts.items(), key=lambda kv: (kv[1], kv[0]))
        is_positive = bool(
            ring_id and n_members >= cfg.positive_component_ring_fraction * comp.size
        )

        # Majority cluster, same pick rule as ring_id -- but unlike ring_id
        # this is not gated behind is_positive: clusters are never "positive",
        # so there is no fraction threshold to gate on. Purely informational,
        # used for the split-isolation check and per-cluster-type reporting.
        cluster_id = ""
        if cluster_counts:
            cluster_id = max(cluster_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]

        out.append(
            Candidate(
                component_id=s.component_id,
                split=splits.by_component[s.component_id].split,
                score=s.score,
                signals={k: v.normalized for k, v in s.signals.items()},
                raw_signals={k: v.raw for k, v in s.signals.items()},
                accounts=set(comp.accounts),
                is_positive=is_positive,
                ring_id=ring_id if is_positive else "",
                has_family=has_family,
                cluster_id=cluster_id,
                n_txns=s.n_txns,
                exposure=s.exposure,
            )
        )
    return out


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def confusion(flags: list[tuple[bool, bool]]) -> dict[str, int]:
    """(predicted, actual) pairs -> counts. Every item lands in exactly one cell."""
    tp = sum(1 for p, a in flags if p and a)
    fp = sum(1 for p, a in flags if p and not a)
    tn = sum(1 for p, a in flags if not p and not a)
    fn = sum(1 for p, a in flags if not p and a)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def prf(c: dict[str, int]) -> dict[str, float]:
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
    }


def score_at(cands: list[Candidate], threshold: float) -> dict[str, float | int]:
    c = confusion([(x.score >= threshold, x.is_positive) for x in cands])
    return {**c, **prf(c)}


def _f1_of(flags: list[tuple[bool, bool]]) -> float:
    return prf(confusion(flags))["f1"]


def best_f1_with_direction(
    values: list[float], actual: list[bool]
) -> tuple[float, str, float]:
    """Best F1 any single threshold on `values` can reach, sweeping BOTH
    directions, and the direction and threshold that achieve it.

    Both directions is not a refinement, it is the difference between a working
    check and a broken one. A `>=`-only sweep is blind to signals where the LOW
    values are the suspicious ones -- `ip_concentration` and `account_newness`
    are both inverted in this benchmark, and a `>=`-only sweep reported them at
    F1 0.38 when they actually reach 0.97 and 0.94. A signal that separated the
    classes *perfectly* in the inverted direction would have passed the
    "no single signal separates perfectly" guard untouched, which is precisely
    the case that guard exists to catch. See bugs.md RISK-001.
    """
    best_f1, best_dir, best_t = 0.0, ">=", 0.0
    for t in sorted(set(values)):
        up = _f1_of([(v >= t, a) for v, a in zip(values, actual)])
        if up > best_f1:
            best_f1, best_dir, best_t = up, ">=", t
        down = _f1_of([(v <= t, a) for v, a in zip(values, actual)])
        if down > best_f1:
            best_f1, best_dir, best_t = down, "<=", t
    return round(best_f1, 4), best_dir, best_t


def best_f1_over_thresholds(values: list[float], actual: list[bool]) -> float:
    """Best F1 any single threshold on `values` can reach, either direction."""
    return best_f1_with_direction(values, actual)[0]


# --------------------------------------------------------------------------
# threshold freeze
# --------------------------------------------------------------------------


def select_threshold(cfg: Config, validation: list[Candidate]) -> tuple[float, dict]:
    """Pick the operating threshold on VALIDATION candidates only.

    Takes validation candidates as its whole input. There is no parameter
    through which test data could reach it -- the protocol is enforced by the
    signature, not by remembering to be careful.
    """
    assert all(c.split == "validation" for c in validation), (
        "select_threshold received non-validation candidates -- "
        "this would be threshold fitting on held-out data"
    )
    best_t, best_f1 = 0.5, -1.0
    for i in range(101):
        t = i / 100.0
        f1 = float(score_at(validation, t)["f1"])
        if f1 > best_f1:
            best_t, best_f1 = t, f1

    meta = {
        "threshold": best_t,
        "selection_metric": "f1",
        "selected_on": "validation",
        "validation_components": len(validation),
        "validation_f1_at_threshold": round(best_f1, 4),
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }
    return best_t, meta


def freeze_threshold(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def load_threshold(path: Path) -> float:
    """Read the frozen threshold back. The runner uses this rather than the
    in-memory value, so the file is genuinely load-bearing."""
    return float(json.loads(path.read_text(encoding="utf-8"))["threshold"])


# --------------------------------------------------------------------------
# held-out evaluation
# --------------------------------------------------------------------------


def ring_recovery(cfg: Config, test: list[Candidate], labels: list[Label],
                  threshold: float) -> dict[str, float | int]:
    """Fraction of test rings surfaced by at least one flagged component.

    A ring counts as recovered when a flagged component covers at least
    `positive_component_ring_fraction` of its members -- the same coverage bar
    the ground-truth rule uses, so the two cannot disagree.
    """
    members: dict[str, set[str]] = defaultdict(set)
    for lb in labels:
        if lb.ring_id and lb.active_period == "test":
            members[lb.ring_id].add(lb.account_id)

    recovered = 0
    for ring_id, accts in members.items():
        for cand in test:
            if cand.score < threshold:
                continue
            covered = len(cand.accounts & accts)
            if covered >= cfg.positive_component_ring_fraction * len(accts):
                recovered += 1
                break
    total = len(members)
    return {
        "rings_in_test": total,
        "rings_recovered": recovered,
        "ring_recovery_rate": round(recovered / total, 4) if total else 0.0,
    }


def evaluate(cfg: Config, test: list[Candidate], labels: list[Label],
             threshold: float) -> dict:
    """Held-out metrics at a frozen threshold. Never selects anything."""
    assert all(c.split == "test" for c in test), "evaluate() got non-test candidates"

    primary = score_at(test, threshold)
    assert (primary["tp"] + primary["fp"] + primary["tn"] + primary["fn"]
            == len(test)), "confusion matrix does not account for every component"

    # Secondary unit: every account inherits its component's score. Accounts in
    # no component (graph singletons) are out of scope -- they were never
    # candidates, and counting them as true negatives would flatter the FPR.
    ring_accounts = {lb.account_id for lb in labels if lb.ring_id}
    acct_flags = [
        (c.score >= threshold, a in ring_accounts) for c in test for a in sorted(c.accounts)
    ]
    acct_conf = confusion(acct_flags)

    return {
        "primary": {"unit": "component", **primary,
                    **ring_recovery(cfg, test, labels, threshold)},
        "secondary": {"unit": "account", "scored_accounts": len(acct_flags),
                      **acct_conf, **prf(acct_conf),
                      "note": "accounts in no candidate component are excluded"},
        "threshold": threshold,
        "threshold_selected_on": "validation",
        "ground_truth_rule": GROUND_TRUTH_RULE,
        "split_boundaries": {k: list(v) for k, v in cfg.split_boundaries.items()},
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }


# --------------------------------------------------------------------------
# baselines used by the non-triviality panel
# --------------------------------------------------------------------------


def shared_device_baseline_f1(cands: list[Candidate]) -> float:
    """Best F1 from the single rule 'many accounts share one device'.

    If this matches the graph scorer, the graph is decoration -- which is why
    `max_shared_device_baseline_f1` is a hard bound rather than a note.
    """
    return best_f1_over_thresholds(
        [c.raw_signals["device_sharing"] for c in cands], [c.is_positive for c in cands]
    )


def single_signal_f1(cands: list[Candidate]) -> dict[str, float]:
    return {name: d["f1"] for name, d in single_signal_detail(cands).items()}


def single_signal_detail(cands: list[Candidate]) -> dict[str, dict]:
    """Per signal: best achievable F1, and which direction/threshold achieves it.

    The direction is reported because an inverted signal is a finding in its own
    right -- it means the signal is scored with the wrong sign.
    """
    actual = [c.is_positive for c in cands]
    out: dict[str, dict] = {}
    for name in SIGNALS:
        f1, direction, t = best_f1_with_direction(
            [c.raw_signals[name] for c in cands], actual
        )
        out[name] = {"f1": f1, "direction": direction, "threshold": round(t, 4)}
    return out
