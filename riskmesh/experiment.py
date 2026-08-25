"""Generator experiments, with the design/test boundary enforced structurally.

An experiment changes the generator and asks whether a signal improves. That is
exactly the situation where it is easiest to cheat without meaning to: look at
the test split, dislike the answer, adjust, look again. `select_threshold()`
already prevents that for thresholds by taking only validation candidates. This
module gives experiment design the same shape of guarantee, rather than relying
on the author to remember:

1. `design_view()` is the only accessor an experiment uses while it is being
   designed or tuned. It returns train+validation rows and raises `TestSetLeak`
   if a test row is present -- so an experiment cannot read test data through the
   supported path at all.
2. `freeze_experiment()` writes the hypothesis, the generator delta and the
   design-split measurements to disk **before** any test data is touched.
3. `require_frozen()` refuses to hand over test candidates until that record
   exists. The file is load-bearing: no record, no test evaluation.

The record is what an auditor reads afterwards. It says what was predicted, on
what evidence, before the held-out answer was known.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import SIGNALS, Config
from .evaluate import Candidate, build_candidates
from .generate import generate
from .graph import build_graph
from .score import score_all
from .split import assign_splits

DESIGN_SPLITS = ("train", "validation")


class TestSetLeak(AssertionError):
    """Raised when test data would be read outside the frozen protocol."""


def design_view(candidates: list[Candidate]) -> list[Candidate]:
    """The only rows an experiment may see while it is being designed."""
    leaked = [c.component_id for c in candidates if c.split == "test"]
    view = [c for c in candidates if c.split in DESIGN_SPLITS]
    if any(c.split == "test" for c in view):  # pragma: no cover - belt and braces
        raise TestSetLeak("design_view returned test rows")
    if leaked and len(view) + len(leaked) != len(candidates):
        raise TestSetLeak("candidate list has splits outside train/validation/test")
    return view


def held_out_view(candidates: list[Candidate], record_path: Path) -> list[Candidate]:
    """Test rows -- available only once the experiment record is on disk."""
    if not record_path.exists():
        raise TestSetLeak(
            f"{record_path.name} has not been frozen. The experiment design and its "
            "train+validation measurements must be recorded before the test split is "
            "read, or the comparison is not held out."
        )
    return [c for c in candidates if c.split == "test"]


def ring_vs_family(cfg: Config, view: list[Candidate]) -> dict[str, dict[str, float]]:
    """Per-signal normalised means split by negative type.

    Ring-vs-background is the easy half of the problem and every signal already
    does it; ring-vs-family is the number that decides whether a signal works.
    """
    pos = [c for c in view if c.is_positive]
    fam = [c for c in view if not c.is_positive and c.has_family]
    bg = [c for c in view if not c.is_positive and not c.has_family]
    out: dict[str, dict[str, float]] = {}
    for name in SIGNALS:
        r = statistics.fmean([c.signals[name] for c in pos]) if pos else 0.0
        f = statistics.fmean([c.signals[name] for c in fam]) if fam else 0.0
        b = statistics.fmean([c.signals[name] for c in bg]) if bg else 0.0
        out[name] = {
            "ring": round(r, 4), "family": round(f, 4), "background": round(b, 4),
            "ring_minus_family": round(r - f, 4),
            "weight": round(cfg.weights[name], 4),
        }
    return out


def build(cfg: Config) -> list[Candidate]:
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)
    splits = assign_splits(cfg, graph, labels)
    return build_candidates(cfg, graph, scores, splits, labels)


def freeze_experiment(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# E1
# --------------------------------------------------------------------------

E1_NAME = "E1-family-independent-temporal"

E1_HYPOTHESIS = (
    "RISK-003's residual defect is in the generator, not the feature. Family "
    "co-bursts are emitted by the same _add_burst path as ring bursts -- same "
    "30-minute window, same single merchant, families at higher participation "
    "(0.9 vs 0.75) -- so no definition of temporal_burst can separate them. "
    "Removing the family co-burst makes household activity what a household's "
    "activity actually is: each member transacting on their own routine, drawn "
    "independently per account, with no shared merchant-and-minute rendezvous. "
    "Predicted: temporal_burst ring-minus-family turns clearly positive. Also "
    "predicted, and the reason this may not be adopted: family components become "
    "easier, so the non-triviality margin that Tier 0 bought by making the two "
    "bursts identical will shrink."
)

E1_GENERATOR_DELTA = {
    "family_coburst_rate": {"from": 0.60, "to": 0.0},
    "changed": "family temporal generation only",
    "unchanged": [
        "ring injector (burst rate, window, participation, merchant)",
        "temporal_burst Variant B definition",
        "all scorer weights",
        "device_sharing, instrument_sharing, merchant_concentration, ip_sharing, "
        "account_newness, failure_refund_rate definitions",
        "family size, signup, refund, device and IP sharing",
    ],
    "note": (
        "Implemented as a config value rather than a new code path: at "
        "family_coburst_rate 0.0 the family injector never calls _add_burst, so "
        "family activity comes only from _emit, which already draws each "
        "account's transactions independently with per-account diurnal timing. "
        "Family transaction VOLUME (randint(8,16)) is deliberately left alone -- "
        "E1 is scoped to temporal coordination, not activity rate."
    ),
}


def run_e1(out: Path, base: Config | None = None) -> dict[str, Any]:
    base = base or Config()
    cfg = replace(base, family_coburst_rate=0.0)
    record_path = out / "experiment_e1.json"

    # --- design phase: train+validation only, structurally --------------------
    candidates = build(cfg)
    view = design_view(candidates)

    baseline_view = design_view(build(base))
    meta = {
        "experiment": E1_NAME,
        "hypothesis": E1_HYPOTHESIS,
        "generator_delta": E1_GENERATOR_DELTA,
        "designed_on": list(DESIGN_SPLITS),
        "design_components": len(view),
        "seed": cfg.seed,
        "baseline_config_fingerprint": base.fingerprint(),
        "experiment_config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
        "design_split_ring_vs_family": {
            "baseline": ring_vs_family(base, baseline_view),
            "experiment": ring_vs_family(cfg, view),
        },
    }
    freeze_experiment(record_path, meta)

    # --- only now may test be read -------------------------------------------
    held_out = held_out_view(candidates, record_path)
    meta["held_out_components"] = len(held_out)
    return {"cfg": cfg, "candidates": candidates, "record": meta,
            "record_path": record_path}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "out"
    result = run_e1(out)
    rvf = result["record"]["design_split_ring_vs_family"]
    print(f"{E1_NAME}  (designed on {'+'.join(DESIGN_SPLITS)} only)")
    print(f"record frozen at {result['record_path']}\n")
    print(f"{'signal':24} {'ring':>7} {'family':>7} {'backgr':>7} "
          f"{'r-f base':>9} {'r-f E1':>8} {'moved':>8}")
    print("-" * 76)
    for name in SIGNALS:
        b, e = rvf["baseline"][name], rvf["experiment"][name]
        print(f"{name:24} {e['ring']:7.3f} {e['family']:7.3f} {e['background']:7.3f} "
              f"{b['ring_minus_family']:+9.3f} {e['ring_minus_family']:+8.3f} "
              f"{e['ring_minus_family'] - b['ring_minus_family']:+8.3f}")
