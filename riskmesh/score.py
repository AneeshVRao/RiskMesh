"""Deterministic risk score per connected component (PRD Tier 1 baseline).

Seven signals, each computed as a **raw** value and a **normalised** [0,1] value.
The score is the weighted sum of the normalised values, clipped to [0,1], with
weights from `config.py` that sum to exactly 1.00.

Each signal also carries a `detail` string -- "8/9 accounts within 30 minutes"
rather than a bare 0.89. That string is the evidence a Tier 1 investigator view
or LLM explanation needs, and producing it here means it is derived from the
same computation as the score instead of being reconstructed later from a float.

`score_component()` takes no label argument, and cannot be given one: its
signature is (config, component, context). Leakage is prevented by the shape of
the function, not only by a test asserting good behaviour.

A note on `ip_concentration`. In Tier 0 the rings share a *device*, while the
family hard negatives share a *home IP*, so this signal fires harder on the
legitimate clusters than on the abusive ones. That is deliberate and left in
place: shared-IP concentration is a real risk signal in production, hard
negatives really do trigger it, and the whole point of the exercise is to price
that false-positive pressure rather than to define it away.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import NamedTuple

from .config import SIGNALS, Config
from .generate import Txn
from .graph import Component, Graph


class Signal(NamedTuple):
    raw: float
    normalized: float
    weight: float
    contribution: float
    detail: str


@dataclass
class ScoringContext:
    """Population-level facts a component is scored against.

    Passed in rather than recomputed per component so every component is judged
    against the same baseline -- and so nothing here can reach for a label.
    """

    common_infra: set[str]  # attribute values ruled common infrastructure
    base_anomaly_rate: float  # population refund+failure rate

    @classmethod
    def from_graph(cls, cfg: Config, txns: list[Txn], graph: Graph) -> "ScoringContext":
        common = {v for values in graph.capped.values() for v in values}
        bad = sum(1 for t in txns if t.is_refund or t.status == "failed")
        return cls(common_infra=common, base_anomaly_rate=bad / max(1, len(txns)))


@dataclass
class ComponentScore:
    component_id: str
    size: int
    n_txns: int
    exposure: float
    score: float
    signals: dict[str, Signal]


def _clip(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _max_accounts_per(comp: Component, attr: str) -> tuple[str, int]:
    holders: dict[str, set[str]] = defaultdict(set)
    for t in comp.txns:
        holders[getattr(t, attr)].add(t.account_id)
    if not holders:
        return "", 0
    value, accounts = max(holders.items(), key=lambda kv: (len(kv[1]), kv[0]))
    return value, len(accounts)


def _burst(comp: Component, window: int) -> tuple[int, int]:
    """Most distinct accounts active inside any `window`-minute span.

    Sliding window over time-sorted transactions -- the signal that separates a
    coordinated ring from a family that merely shares a tablet.
    """
    events = sorted((t.ts_minute, t.account_id) for t in comp.txns)
    counts: Counter[str] = Counter()
    best = 0
    lo = 0
    for ts, acct in events:
        counts[acct] += 1
        while events[lo][0] < ts - window:
            drop = events[lo][1]
            counts[drop] -= 1
            if counts[drop] == 0:
                del counts[drop]
            lo += 1
        best = max(best, len(counts))
    return best, len(comp.accounts)


def _top_share(comp: Component, attr: str, exclude: set[str]) -> tuple[str, float, int]:
    counts = Counter(
        getattr(t, attr) for t in comp.txns if getattr(t, attr) not in exclude
    )
    if not counts:
        return "", 0.0, 0
    value, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return value, n / len(comp.txns), n


def score_component(cfg: Config, comp: Component, ctx: ScoringContext) -> ComponentScore:
    """Score one component. No labels in, by construction."""
    n_txns = len(comp.txns)
    w = cfg.weights
    sig: dict[str, Signal] = {}

    def add(name: str, raw: float, norm: float, detail: str) -> None:
        clipped = _clip(norm)
        sig[name] = Signal(raw, clipped, w[name], round(w[name] * clipped, 6), detail)

    # 1. device sharing -- structural, and the ring's defining attribute
    device, k = _max_accounts_per(comp, "device_id")
    add("device_sharing", k, (k - 1) / max(1, cfg.max_device_degree - 1),
        f"{k} accounts share device {device}")

    # 2. temporal burst -- coordination in time, the ring/family discriminator
    burst, n_acc = _burst(comp, cfg.burst_window_minutes)
    add("temporal_burst", burst, (burst - 1) / max(1, cfg.ring_size_max - 1),
        f"{burst}/{n_acc} accounts within {cfg.burst_window_minutes} minutes")

    # 3. instrument sharing -- partial card overlap
    pi, k_pi = _max_accounts_per(comp, "instrument_id")
    add("instrument_sharing", k_pi, (k_pi - 1) / max(1, cfg.max_instrument_degree - 1),
        f"{k_pi} accounts share instrument {pi}")

    # 4. refund/failure pressure, measured against the population baseline
    bad = sum(1 for t in comp.txns if t.is_refund or t.status == "failed")
    rate = bad / max(1, n_txns)
    base = ctx.base_anomaly_rate
    add("failure_refund_rate", round(rate, 4), (rate - base) / max(1e-9, 3 * base),
        f"{rate:.0%} refund/failure vs {base:.0%} baseline")

    # 5. IP concentration, ignoring common infrastructure (NAT and friends)
    ip, share_ip, n_ip = _top_share(comp, "ip_id", ctx.common_infra)
    add("ip_concentration", round(share_ip, 4), share_ip,
        f"{n_ip}/{n_txns} transactions from {ip or 'no shared IP'}")

    # 6. account newness -- mule accounts are young, households are not
    ages = [t.account_age_days for t in comp.txns]
    median_age = statistics.median(ages) if ages else 0.0
    add("account_newness", median_age, 1.0 - median_age / 180.0,
        f"median account age {median_age:.0f} days")

    # 7. merchant concentration -- cash-out through one merchant
    merchant, share_m, n_m = _top_share(comp, "merchant_id", set())
    add("merchant_concentration", round(share_m, 4), share_m,
        f"{n_m}/{n_txns} transactions at {merchant}")

    assert set(sig) == set(SIGNALS), "scorer and config disagree on the signal set"
    score = _clip(sum(s.contribution for s in sig.values()))

    return ComponentScore(
        component_id=comp.component_id,
        size=comp.size,
        n_txns=n_txns,
        exposure=round(sum(t.amount for t in comp.txns if not t.is_refund), 2),
        score=round(score, 6),
        signals=sig,
    )


def score_all(cfg: Config, txns: list[Txn], graph: Graph) -> list[ComponentScore]:
    ctx = ScoringContext.from_graph(cfg, txns, graph)
    return [score_component(cfg, c, ctx) for c in graph.components]


if __name__ == "__main__":
    from .generate import generate
    from .graph import build_graph

    cfg = Config()
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)

    assert all(0.0 <= s.score <= 1.0 for s in scores)
    assert all(set(s.signals) == set(SIGNALS) for s in scores)
    ctx = ScoringContext.from_graph(cfg, txns, graph)
    assert score_component(cfg, graph.components[0], ctx) == scores[0], "not deterministic"

    lab = {lb.account_id: lb for lb in labels}
    by_id = {c.component_id: c for c in graph.components}

    def kind(s: ComponentScore) -> str:
        comp = by_id[s.component_id]
        if any(lab[a].ring_id for a in comp.accounts):
            return "ring"
        if any(lab[a].cluster_id for a in comp.accounts):
            return "family"
        return "background"

    for k in ("ring", "family", "background"):
        vals = [s.score for s in scores if kind(s) == k]
        if vals:
            print(f"{k:11s} n={len(vals):3d}  score min={min(vals):.3f} "
                  f"med={statistics.median(vals):.3f} max={max(vals):.3f}")

    top = max(scores, key=lambda s: s.score)
    print(f"\ntop component {top.component_id}  score={top.score:.3f}  size={top.size}")
    for name in SIGNALS:
        s = top.signals[name]
        print(f"  {name:22s} raw={s.raw:>8.2f} norm={s.normalized:.2f} "
              f"w={s.weight:.2f}  {s.detail}")
    print("\nphase 5 checks ok")
