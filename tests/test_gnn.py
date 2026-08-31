"""riskmesh.gnn checks. Plain asserts, no framework:  python tests/test_gnn.py

Four checks, per `graphsage_protocol.md` and `task_today.md`:

  01  the deliberately-overfit G3 candidate is refused by the gate -- proves
      the gate fires against GraphSAGE, not just against hand-picked weight
      vectors or XGBoost configurations. (Per task_today.md: if G3 is ever
      NOT refused, this check falls back to proving the gate still fires on
      *some* candidate, rather than silently dropping the check.)
  02  select_gnn_model() asserts it received design-only candidates and
      raises on a test row, mirroring select_weights() / select_xgboost_model().
  03  evaluate_frozen_gnn_policy() raises GNNPolicyNotFrozen before the
      freeze file exists.
  04  refitting the same frozen hyperparameters twice on the same data
      produces the same prediction for a given component (determinism, to
      the extent torch's own CPU determinism guarantees allow, per
      graphsage_protocol.md §2.3).

Does not touch tests/test_riskmesh.py, tests/test_api.py or tests/test_ml.py.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch

from riskmesh.config import Config
from riskmesh.costmodel import derive_costs
from riskmesh.evaluate import build_candidates
from riskmesh.generate import generate
from riskmesh.gnn import (
    CANDIDATES,
    GNNPolicyNotFrozen,
    build_component_graphs,
    evaluate_frozen_gnn_policy,
    fit_model,
    select_gnn_model,
)
from riskmesh.graph import build_graph
from riskmesh.score import score_all
from riskmesh.split import assign_splits

PASSED: list[str] = []


def check(name: str) -> None:
    PASSED.append(name)
    print(f"  ok   {name}")


def build(cfg: Config):
    txns, labels = generate(cfg)
    graph = build_graph(cfg, txns)
    scores = score_all(cfg, txns, graph)
    splits = assign_splits(cfg, graph, labels)
    return graph, build_candidates(cfg, graph, scores, splits, labels)


def test_01_gate_fires_against_g3(cfg: Config, design, graph, costs) -> None:
    """graphsage_protocol.md §2.2: G3_unregularised (2 layers, hidden dim 32,
    no weight decay, many epochs) is deliberately overfit-prone and expected
    to be refused, the same role X4_unregularised played for XGBoost. If it
    is ever NOT refused, this proves the gate still fires on some candidate
    rather than silently dropping the check.
    """
    result = select_gnn_model(cfg, design, graph, costs)
    row = next(r for r in result["candidates"] if r["policy"] == "G3_unregularised")
    if row["feasible"]:
        refused = [r for r in result["candidates"] if not r["feasible"]]
        assert refused, (
            "G3_unregularised was NOT refused, AND no other candidate was "
            "refused either -- the gate has stopped firing against GraphSAGE "
            "entirely"
        )
        check(
            "01 G3_unregularised was feasible (a surprise vs. "
            "graphsage_protocol.md §2.2's expectation), but the gate still "
            f"fired against {[r['policy'] for r in refused]} -- not silently "
            "dropped"
        )
    else:
        assert row["refused_by"] in ("PanelGateFailure", "DifficultyGateFailure")
        check(f"01 G3_unregularised refused by the gate ({row['refused_by']}) -- "
              "the gate fires against GraphSAGE, not only against weight "
              "vectors or XGBoost")


def test_02_select_asserts_design_only(cfg: Config, cands, graph, costs) -> None:
    design = [c for c in cands if c.split in ("train", "validation")]
    test_rows = [c for c in cands if c.split == "test"]
    assert test_rows, "no test rows to contaminate the design view with"
    contaminated = design + test_rows[:1]
    try:
        select_gnn_model(cfg, contaminated, graph, costs)
    except AssertionError:
        pass
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError(
            "select_gnn_model accepted a candidate from the test split -- "
            "this would be model fitting/gating on held-out data"
        )
    check("02 select_gnn_model refuses a design view containing a test row")


def test_03_frozen_guard(cfg: Config, cands, graph, tmp: Path) -> None:
    design = [c for c in cands if c.split in ("train", "validation")]
    policy_path = tmp / "graphsage_policy_missing.json"
    assert not policy_path.exists()
    try:
        # Full candidate list, not a pre-filtered test view: the guard must
        # raise before ever reading .split == "test" off any of them.
        evaluate_frozen_gnn_policy(cfg, design, cands, graph, policy_path)
    except GNNPolicyNotFrozen:
        pass
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError(
            "evaluate_frozen_gnn_policy read the test split before any "
            "policy was frozen to disk"
        )
    check("03 evaluate_frozen_gnn_policy raises GNNPolicyNotFrozen before the "
          "freeze file exists")


def test_04_determinism(cfg: Config, cands, graph) -> None:
    """Refit each of the three frozen hyperparameter configurations twice on
    identical train rows and compare validation predictions.

    Neural-network training has run-to-run variance beyond what a fixed seed
    alone controls in general (graphsage_protocol.md §2.3) -- this asserts
    exact equality because that is the finding actually observed on the
    installed torch version, CPU-only, single-process, with
    `torch.manual_seed()` and `torch.use_deterministic_algorithms(True)`
    both set. This is a plain observation of what happened in this
    environment, not a guarantee this project makes about every future
    torch release or every machine -- if this test is ever seen to fail
    after a torch upgrade or on different hardware, that is the finding to
    record here, not a reason to loosen the assertion into a flaky
    tolerance.
    """
    train = [c for c in cands if c.split == "train"]
    validation = [c for c in cands if c.split == "validation"]
    graphs = build_component_graphs(cfg, graph)
    for name, hyperparams in CANDIDATES.items():
        model_a = fit_model(cfg, hyperparams, train, graphs)
        model_b = fit_model(cfg, hyperparams, train, graphs)
        with torch.no_grad():
            scored_a = [float(torch.sigmoid(model_a(graphs[c.component_id])))
                        for c in validation]
            scored_b = [float(torch.sigmoid(model_b(graphs[c.component_id])))
                        for c in validation]
        for c, a, b in zip(validation, scored_a, scored_b):
            assert a == b, (
                f"{name} is not deterministic on torch {torch.__version__}: "
                f"component {c.component_id} scored {a} then {b} from two "
                "fits with the same seed on identical data"
            )
    check(f"04 determinism: refitting each of {len(CANDIDATES)} candidates "
          f"twice gives bit-identical validation predictions on installed "
          f"torch {torch.__version__} (CPU, torch.manual_seed + "
          "use_deterministic_algorithms)")


def main() -> int:
    cfg = Config()
    graph, cands = build(cfg)
    design = [c for c in cands if c.split in ("train", "validation")]
    costs = derive_costs(design)

    tmp = Path(tempfile.mkdtemp(prefix="riskmesh_gnn_test_"))
    try:
        print(f"\nriskmesh.gnn checks  (seed {cfg.seed}, config {cfg.fingerprint()}, "
              f"torch {torch.__version__})\n")
        test_01_gate_fires_against_g3(cfg, design, graph, costs)
        test_02_select_asserts_design_only(cfg, cands, graph, costs)
        test_03_frozen_guard(cfg, cands, graph, tmp)
        test_04_determinism(cfg, cands, graph)
        print(f"\n{len(PASSED)}/4 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
