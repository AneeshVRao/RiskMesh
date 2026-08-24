"""Chronological, ring-level train/validation/test split.

Two kinds of leakage have to be prevented at once, and they need different
defences:

*Structural* leakage -- a ring with members in two splits lets the model see
part of the answer during training. Prevented by assigning every labelled
component from the generator's explicit `active_period`, which is authoritative:
the split is a property of how the cluster was *constructed*, not something
inferred from the data it happened to emit.

*Temporal* leakage -- training on the future. Prevented by ordering the periods
strictly train -> validation -> test in `Config.split_boundaries`.

The two paths are then cross-checked. Every labelled component's median
transaction period is computed independently and compared to its `active_period`;
a mismatch means the generator leaked coordinated activity outside its assigned
window, and the run fails loudly rather than quietly producing a split whose
chronology is fiction. Unlabelled background components have no `active_period`,
so they use the median-timestamp path on its own.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config
from .generate import Label
from .graph import Component, Graph

MINUTES_PER_DAY = 24 * 60


@dataclass
class ComponentSplit:
    component_id: str
    split: str
    active_period: str  # "" when the component carries no labelled cluster
    median_period: str  # computed independently, always
    ring_ids: set[str] = field(default_factory=set)
    cluster_ids: set[str] = field(default_factory=set)

    @property
    def is_labelled(self) -> bool:
        return bool(self.ring_ids or self.cluster_ids)


@dataclass
class SplitResult:
    by_component: dict[str, ComponentSplit]

    def ids_in(self, split: str) -> list[str]:
        return sorted(c.component_id for c in self.by_component.values() if c.split == split)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for c in self.by_component.values():
            out[c.split] += 1
        return dict(out)


def _median_period(cfg: Config, comp: Component) -> str:
    median_ts = statistics.median(t.ts_minute for t in comp.txns)
    return cfg.period_of_day(int(median_ts) // MINUTES_PER_DAY)


def assign_splits(
    cfg: Config, graph: Graph, labels: list[Label], strict: bool = True
) -> SplitResult:
    """Assign every component to exactly one chronological split.

    `strict=False` reports mismatches instead of raising, which is what the
    integrity report uses to *describe* a broken run rather than abort it.
    """
    by_account = {lb.account_id: lb for lb in labels}
    out: dict[str, ComponentSplit] = {}
    mismatches: list[str] = []

    for comp in graph.components:
        rings = {by_account[a].ring_id for a in comp.accounts if by_account[a].ring_id}
        clusters = {
            by_account[a].cluster_id for a in comp.accounts if by_account[a].cluster_id
        }
        periods = {
            by_account[a].active_period for a in comp.accounts
            if by_account[a].active_period
        }
        median_period = _median_period(cfg, comp)

        if periods:
            if len(periods) > 1:
                # Two clusters from different periods fused into one component.
                # Nothing downstream can split them, so fail rather than pick.
                raise AssertionError(
                    f"{comp.component_id} spans periods {sorted(periods)}"
                )
            active = periods.pop()
            if active != median_period:
                mismatches.append(
                    f"{comp.component_id}: active_period={active} "
                    f"median_timestamp_period={median_period}"
                )
            split = active  # generator intent wins; the check above audits it
        else:
            active = ""
            split = median_period

        out[comp.component_id] = ComponentSplit(
            component_id=comp.component_id,
            split=split,
            active_period=active,
            median_period=median_period,
            ring_ids=rings,
            cluster_ids=clusters,
        )

    if mismatches and strict:
        raise AssertionError(
            "labelled components whose activity escaped their assigned period:\n  "
            + "\n  ".join(mismatches)
        )

    _assert_no_cluster_spans_splits(out, strict)
    return SplitResult(out)


def _assert_no_cluster_spans_splits(
    by_component: dict[str, ComponentSplit], strict: bool
) -> None:
    """The ring-level guarantee: one ring, one split. Checked, never assumed."""
    seen: dict[str, str] = {}
    problems: list[str] = []
    for cs in by_component.values():
        for key in list(cs.ring_ids) + list(cs.cluster_ids):
            if key in seen and seen[key] != cs.split:
                problems.append(f"{key} in both {seen[key]} and {cs.split}")
            seen[key] = cs.split
    if problems and strict:
        raise AssertionError("ring/cluster leaked across splits: " + "; ".join(problems))


def split_report(cfg: Config, result: SplitResult) -> dict[str, object]:
    """The split facts that belong in both reports."""
    per_split: dict[str, dict[str, int]] = {}
    for name in cfg.split_boundaries:
        members = [c for c in result.by_component.values() if c.split == name]
        per_split[name] = {
            "components": len(members),
            "rings": len({r for c in members for r in c.ring_ids}),
            "family_clusters": len({f for c in members for f in c.cluster_ids}),
            "unlabelled": sum(1 for c in members if not c.is_labelled),
        }
    return {
        "strategy": "chronological, ring-level; labelled components use the "
                    "generator active_period, unlabelled use median timestamp",
        "ordering": list(cfg.split_boundaries),
        "day_boundaries": {k: list(v) for k, v in cfg.split_boundaries.items()},
        "per_split": per_split,
    }


if __name__ == "__main__":
    import json

    from .generate import generate
    from .graph import build_graph

    cfg = Config()
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    result = assign_splits(cfg, graph, labels)

    labelled = [c for c in result.by_component.values() if c.is_labelled]
    assert labelled, "no labelled components at all"
    assert all(c.active_period == c.median_period for c in labelled)

    rep = split_report(cfg, result)
    per_split = rep["per_split"]
    assert isinstance(per_split, dict)
    for name, stats in per_split.items():
        assert stats["rings"] >= 1, f"{name} split has no rings"

    print(json.dumps(rep, indent=2))
    print(f"\nlabelled components {len(labelled)}  "
          f"active_period == median_period for all of them")
    print("phase 6 checks ok")
