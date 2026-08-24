"""Relationship graph over accounts, devices, IPs and payment instruments, plus
the hygiene rules that stop common infrastructure from merging the population.

The PRD calls this out as its own must-have feature, and it is the part most
easily got wrong: link accounts on every shared attribute and a single carrier
NAT IP drags six hundred unrelated people into one "ring". Three rules prevent
that, all configurable and all reported:

1. **Merchants never link.** Everybody shops at the popular merchants, so
   merchant edges merge everything. Merchants stay available as evidence but
   take no part in forming components.

2. **Degree cap.** An attribute used by more than `max_ip_degree` /
   `max_device_degree` distinct accounts is *common infrastructure* and stops
   linking. The caps sit above the largest legitimate ring, so a real ring is
   never capped away, and `Graph.capped` lists every node that was, so the
   effect stays auditable instead of invisible.

3. **Minimum edge weight.** An account must use an attribute at least
   `min_edge_txns` times before the edge links. One incidental touch -- a
   borrowed phone, a single session on a hotel IP -- should not weld two
   populations together.

Union-find over whatever survives. Components of one account are dropped: a lone
account is not a candidate ring, and keeping them would swamp every distribution
in the integrity report.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config
from .generate import Txn

# Attribute fields that can link accounts, and the config cap that governs each.
LINKING_ATTRS: dict[str, str] = {
    "device_id": "max_device_degree",
    "ip_id": "max_ip_degree",
    "instrument_id": "max_instrument_degree",
}


@dataclass
class Component:
    """One candidate cluster: the accounts, and the transactions they made."""

    component_id: str
    accounts: set[str] = field(default_factory=set)
    txns: list[Txn] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.accounts)


@dataclass
class Graph:
    components: list[Component]
    capped: dict[str, list[str]]  # attribute field -> nodes ruled common infra
    edge_counts: dict[str, dict[str, int]]  # attribute field -> value -> accounts
    dropped_singletons: int


class _UnionFind:
    """Union-find with path halving. Fifteen lines; networkx would be a
    dependency for the same result, and Tier 0 stays dependency-free."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Union by name keeps component ids stable across runs, which the
            # byte-for-byte reproducibility test depends on.
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self.parent[hi] = lo


def _accounts_per_value(txns: list[Txn], attr: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for t in txns:
        out[getattr(t, attr)].add(t.account_id)
    return out


def _usage_counts(txns: list[Txn], attr: str) -> dict[tuple[str, str], int]:
    """How many times each account used each attribute value (rule 3)."""
    out: dict[tuple[str, str], int] = defaultdict(int)
    for t in txns:
        out[(t.account_id, getattr(t, attr))] += 1
    return out


def build_graph(cfg: Config, txns: list[Txn]) -> Graph:
    """Link accounts through shared attributes, then cut the links that lie."""
    uf = _UnionFind()
    capped: dict[str, list[str]] = {}
    edge_counts: dict[str, dict[str, int]] = {}

    for attr, cap_name in LINKING_ATTRS.items():
        cap = getattr(cfg, cap_name)
        holders = _accounts_per_value(txns, attr)
        usage = _usage_counts(txns, attr)
        edge_counts[attr] = {v: len(a) for v, a in holders.items()}

        common: list[str] = []
        for value, accounts in sorted(holders.items()):
            # Rule 2: too many distinct accounts -> common infrastructure.
            if len(accounts) > cap:
                common.append(value)
                continue
            # Rule 3: only accounts that really use it get linked through it.
            linked = sorted(a for a in accounts if usage[(a, value)] >= cfg.min_edge_txns)
            for other in linked[1:]:
                uf.union(linked[0], other)
        capped[attr] = common

    # Every account is a node even if nothing links it, so singletons are
    # counted rather than silently vanishing.
    for t in txns:
        uf.find(t.account_id)

    grouped: dict[str, Component] = {}
    for t in txns:
        root = uf.find(t.account_id)
        comp = grouped.get(root)
        if comp is None:
            comp = grouped[root] = Component(component_id=f"c_{root}")
        comp.accounts.add(t.account_id)
        comp.txns.append(t)

    components = sorted(
        (c for c in grouped.values() if c.size >= 2), key=lambda c: c.component_id
    )
    dropped = sum(1 for c in grouped.values() if c.size < 2)
    return Graph(components, capped, edge_counts, dropped)


if __name__ == "__main__":
    from collections import Counter

    from .generate import generate

    cfg = Config()
    txns, _ = generate(cfg)
    g = build_graph(cfg, txns)

    n_accounts = len({t.account_id for t in txns})
    largest = max((c.size for c in g.components), default=0)
    share = largest / n_accounts
    nat_capped = [ip for ip in g.capped["ip_id"] if ip.startswith("ip_nat")]
    n_nat = sum(1 for ip in g.edge_counts["ip_id"] if ip.startswith("ip_nat"))

    assert share < cfg.max_largest_component_share, f"giant component: {share:.1%}"
    assert len(nat_capped) == n_nat, f"only {len(nat_capped)}/{n_nat} NAT IPs capped"
    assert g.capped, "nothing capped -- hygiene rules are not firing"

    print(f"accounts           {n_accounts}")
    print(f"components (>=2)   {len(g.components)}  singletons dropped {g.dropped_singletons}")
    print(f"largest component  {largest} accounts ({share:.1%}, bound {cfg.max_largest_component_share:.0%})")
    print(f"size distribution  {sorted(Counter(c.size for c in g.components).items())}")
    print(f"capped nodes       " + ", ".join(f"{k}={len(v)}" for k, v in g.capped.items()))
    print(f"NAT IPs capped     {len(nat_capped)}/{n_nat}")
    print("phase 4 checks ok")
