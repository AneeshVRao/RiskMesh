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
from pathlib import Path

from .config import SIGNALS, Config
from .evaluate import (
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

OUT = Path(__file__).resolve().parent.parent / "out"
MINUTES_PER_DAY = 24 * 60


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


def _write_components(path: Path, scores: list[ComponentScore], splits, cands) -> None:
    """Both raw and normalised values per signal, so the evidence a UI or an
    explanation layer needs is already in the file."""
    by_id = {c.component_id: c for c in cands}
    cols = ["component_id", "split", "size", "n_txns", "exposure", "score",
            "is_positive", "ring_id", "has_family"]
    for name in SIGNALS:
        cols += [f"{name}_raw", f"{name}_norm", f"{name}_detail"]

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for s in sorted(scores, key=lambda x: x.component_id):
            c = by_id[s.component_id]
            row = [s.component_id, splits.by_component[s.component_id].split,
                   s.size, s.n_txns, s.exposure, s.score,
                   int(c.is_positive), c.ring_id, int(c.has_family)]
            for name in SIGNALS:
                sig = s.signals[name]
                row += [sig.raw, sig.normalized, sig.detail]
            w.writerow(row)


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
    _write_components(out / "components.csv", scores, splits, candidates)

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
    print(f"\nwrote 6 files to {out}")

    return {"integrity": report, "eval": result, "threshold": frozen}


if __name__ == "__main__":
    main()
