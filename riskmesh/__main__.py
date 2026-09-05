"""One command reproduces the whole Tier 0 benchmark:  python -m riskmesh

Order matters, and it is the order of the protocol:

    generate -> graph -> score -> split -> integrity report
             -> select threshold on VALIDATION -> freeze to disk
             -> read the frozen threshold back -> evaluate on TEST

The threshold is written to `out/threshold.json` and read back before the test
split is touched. That round-trip is deliberate: the frozen file is what an
auditor checks, so it has to be genuinely load-bearing rather than decorative.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from .comparisons import ablation_report, baseline_report
from .config import SIGNALS, Config
from .evaluate import (
    bootstrap_ci,
    build_candidates,
    evaluate,
    freeze_threshold,
    load_threshold,
    select_threshold,
)
from .generate import Label, Txn, generate
from .graph import build_graph
from .integrity import integrity_report, print_report
from .score import ComponentScore, score_all
from .split import assign_splits

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
EXPERIMENTS = ROOT / "experiments"
# Frozen records produced by their own freeze stages, copied into out/ so a
# single `python -m riskmesh` leaves out/ complete for the API to read.
FROZEN_RECORDS = ("weight_policy.json", "abstention_policy.json", "xgboost_policy.json",
                  "graphsage_policy.json")
MINUTES_PER_DAY = 24 * 60

# Attribute fields that can put two accounts on the same node in the UI graph,
# and the node type each becomes. Same fields graph.py links on, plus merchant --
# merchants never link accounts into a component, but the burst story is told
# against one, so the view needs them.
GRAPH_LINKS = (
    ("device_id", "device"),
    ("instrument_id", "instrument"),
    ("ip_id", "ip"),
    ("merchant_id", "merchant"),
)


def _write_transactions(path: Path, txns: list[Txn]) -> None:
    """The transaction stream. Note what is NOT here: no ring, no cluster, no
    class column. Label separation is enforced by this writer."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([*Txn._fields, "day"])
        for t in txns:
            w.writerow([*t, t.ts_minute // MINUTES_PER_DAY])


def _write_labels(path: Path, labels: list[Label]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(Label._fields)
        w.writerows(labels)


def _write_components(path: Path, scores: list[ComponentScore], splits, cands,
                      labels: list[Label]) -> None:
    """Both raw and normalised values per signal, so the evidence a UI or an
    explanation layer needs is already in the file.

    `cluster_type` is looked up from `labels` (via `cluster_id`, not carried
    on `Candidate` itself -- same as `ring_type` never was) so the payload
    layer can tell an office/hostel/retail/family cluster apart instead of
    reading only the boolean `has_family` (review fix: `api/payloads.py` was
    hardcoding every `has_family` component as `"family"`).
    """
    by_id = {c.component_id: c for c in cands}
    cluster_type_by_id = {lb.cluster_id: lb.cluster_type for lb in labels if lb.cluster_id}
    cols = ["component_id", "split", "size", "n_txns", "exposure", "score",
            "is_positive", "ring_id", "has_family", "cluster_id", "cluster_type"]
    for name in SIGNALS:
        cols += [f"{name}_raw", f"{name}_norm", f"{name}_detail"]

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for s in sorted(scores, key=lambda x: x.component_id):
            c = by_id[s.component_id]
            row = [s.component_id, splits.by_component[s.component_id].split,
                   s.size, s.n_txns, s.exposure, s.score,
                   int(c.is_positive), c.ring_id, int(c.has_family), c.cluster_id,
                   cluster_type_by_id.get(c.cluster_id, "")]
            for name in SIGNALS:
                sig = s.signals[name]
                row += [sig.raw, sig.normalized, sig.detail]
            w.writerow(row)


def _write_graph_edges(path: Path, graph) -> None:
    """Account-to-shared-attribute adjacency, per component, for the UI graph.

    Built here rather than in the API for the same reason the scores are: this
    runs inside the fingerprinted pipeline, so `out/graph_edges.json` carries the
    same byte-for-byte reproducibility guarantee as everything else in `out/`.
    Reconstructing it live from transactions.csv would put untested derivation on
    the request path and outside that guarantee.

    A value only one account touches is dropped -- it cannot connect anybody, and
    keeping it would bury the shared device under a hundred private ones. Every
    list is sorted, so the serialisation is stable across runs.
    """
    out: dict[str, dict] = {}
    for comp in sorted(graph.components, key=lambda c: c.component_id):
        nodes, edges = [], []
        for attr, kind in GRAPH_LINKS:
            per_value: dict[str, dict[str, int]] = {}
            for t in comp.txns:
                per_value.setdefault(getattr(t, attr), {}).setdefault(t.account_id, 0)
                per_value[getattr(t, attr)][t.account_id] += 1
            for value, accounts in sorted(per_value.items()):
                if len(accounts) < 2:
                    continue
                nodes.append({"id": value, "type": kind, "degree": len(accounts)})
                for account, n in sorted(accounts.items()):
                    edges.append({"account": account, "node": value,
                                  "kind": kind, "txns": n})
        out[comp.component_id] = {
            "accounts": sorted(comp.accounts),
            "nodes": nodes,
            "edges": edges,
        }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def _copy_frozen_record(src: Path, dst: Path) -> None:
    """Byte copy a frozen record from experiments/ into out/.

    Byte copy, never a json round-trip: re-serialising would risk reordering
    keys or changing spacing, which would break test_18's byte-for-byte
    assertion on a file whose content never changed.

    These records are produced by their own freeze stages (the weight search,
    the abstention freeze), not by this pipeline. They are copied here so that
    `out/` is complete and self-contained after a single `python -m riskmesh`:
    the API reads `out/` and only `out/`, and `experiments/` is provenance.
    Without the copy a fresh clone regenerates out/ and the API still cannot
    start, which is a hole a clean-checkout run should not leave.
    """
    if not src.exists():
        raise FileNotFoundError(
            f"{src} is missing -- it is a frozen record the pipeline copies "
            f"into out/ for the API to read. Restore it from git, or re-run "
            f"the freeze stage that produces it."
        )
    shutil.copyfile(src, dst)


def main(cfg: Config | None = None, out: Path = OUT) -> dict:
    cfg = cfg or Config()
    out.mkdir(parents=True, exist_ok=True)

    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)
    splits = assign_splits(cfg, graph, labels)
    candidates = build_candidates(cfg, graph, scores, splits, labels)

    _write_transactions(out / "transactions.csv", txns)
    _write_labels(out / "labels.csv", labels)
    _write_components(out / "components.csv", scores, splits, candidates, labels)
    _write_graph_edges(out / "graph_edges.json", graph)
    for name in FROZEN_RECORDS:
        _copy_frozen_record(EXPERIMENTS / name, out / name)

    report = integrity_report(cfg, txns, labels, graph, splits, candidates)
    (out / "integrity_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print_report(report)

    # --- threshold: validation only, frozen to disk, then read back ---------
    validation = [c for c in candidates if c.split == "validation"]
    threshold, meta = select_threshold(cfg, validation)
    freeze_threshold(out / "threshold.json", meta)

    frozen = load_threshold(out / "threshold.json")
    test = [c for c in candidates if c.split == "test"]
    result = evaluate(cfg, test, labels, frozen)
    (out / "eval_report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    # --- bootstrap CIs: reporting only, over the split already read above --
    # PRD "Metric Uncertainty" (Should-have). Resamples the SAME test split at
    # the SAME frozen threshold `evaluate()` just read once; see
    # evaluate.bootstrap_ci()'s docstring for the controller ruling on why
    # this is not a second read.
    (out / "bootstrap_ci.json").write_text(
        json.dumps(bootstrap_ci(cfg, test, frozen), indent=2) + "\n",
        encoding="utf-8",
    )

    # --- row 63 baselines and row 70 ablation ------------------------------
    # After the headline read, never before it: these are twelve further frozen
    # configurations, each selecting on validation and reading test once, and
    # none of them may influence the shipped scorer. See implementation_plan.md,
    # "PRD rows 63 and 70", written before any of this ran.
    (out / "baselines.json").write_text(
        json.dumps(baseline_report(cfg, txns, graph, candidates, labels), indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "ablations.json").write_text(
        json.dumps(ablation_report(cfg, labels), indent=2) + "\n",
        encoding="utf-8",
    )

    p, s = result["primary"], result["secondary"]
    print(f"\nheld-out evaluation @ threshold {frozen:.2f} "
          f"(selected on validation, {meta['validation_components']} components)")
    print(f"  component-level  P {p['precision']:.3f}  R {p['recall']:.3f}  "
          f"F1 {p['f1']:.3f}  FPR {p['false_positive_rate']:.3f}   "
          f"[TP {p['tp']} FP {p['fp']} TN {p['tn']} FN {p['fn']}]")
    print(f"  ring recovery    {p['rings_recovered']}/{p['rings_in_test']} "
          f"({p['ring_recovery_rate']:.1%})")
    print(f"  account-level    P {s['precision']:.3f}  R {s['recall']:.3f}  "
          f"F1 {s['f1']:.3f}  FPR {s['false_positive_rate']:.3f}   "
          f"[{s['scored_accounts']} accounts]")
    print(f"\nwrote 14 files to {out}")

    return {"integrity": report, "eval": result, "threshold": frozen}


if __name__ == "__main__":
    main()
