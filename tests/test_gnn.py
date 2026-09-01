"""riskmesh.gnn checks. Plain asserts, no framework:  python tests/test_gnn.py

Four checks, per `graphsage_protocol.md` and `task_today.md`:

  01  the difficulty gate refuses a hand-built, over-separated candidate set
      fed directly to gated_expected_loss() -- proves the gate fires against
      GraphSAGE-shaped input in general, via a property test independent of
      whether any particular hyperparameter configuration happens to
      over-separate on this run's population (task-4-report.md: the
      deliberately-overfit G3_unregularised candidate this check used to
      depend on stopped over-separating once Task 4 raised the population,
      which is a fact about population scale, not about the gate).
      G3_unregularised stays in CANDIDATES and is reported informationally.
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

from riskmesh.config import SIGNALS, Config
from riskmesh.costmodel import DifficultyGateFailure, derive_costs, gated_expected_loss
from riskmesh.evaluate import Candidate, build_candidates
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


def _synthetic_candidate(component_id: str, score: float, is_positive: bool,
                         has_family: bool) -> Candidate:
    """One hand-built candidate. Every signal is the same constant (0.5) for
    every candidate, so no single raw signal can separate the classes and
    `shared_device_baseline_f1` stays far below its 0.85 bound -- only
    `.score` (set directly, bypassing any real scorer) drives the panel's
    class-separation checks.
    """
    flat = {name: 0.5 for name in SIGNALS}
    return Candidate(
        component_id=component_id, split="train", score=score,
        signals=dict(flat), raw_signals=dict(flat),
        accounts={f"{component_id}_a0"}, is_positive=is_positive,
        ring_id=component_id if is_positive else "", has_family=has_family,
        cluster_id="", n_txns=10, exposure=100.0,
    )


def _degenerate_design() -> list[Candidate]:
    """A candidate set that separates positives and negatives by
    construction: most of each class sits cleanly apart, with just enough
    overlap to clear the panel's own bounds (score_distributions_overlap,
    hard_negative_in_positive_range >= 1, positives_below_max_negative >=
    0.20) while failing the stricter costmodel difficulty gates
    (MIN_HARD_NEGATIVES_IN_RANGE = 4, MIN_POSITIVES_BELOW_MAX_NEGATIVE =
    0.45): 14 positives score 0.9, 6 score 0.3; 19 negatives score 0.1, one
    (flagged has_family, so the weak panel bound sees it) scores 0.5. Max
    negative score is 0.5, so only the six 0.3-scoring positives (6/20 =
    0.30) fall below it -- above the panel's 0.20 floor, below the gate's
    0.45 floor -- and only one hard negative (0.5 >= min positive 0.3) lands
    in the positive range -- above the panel's >=1 floor, below the gate's
    >=4 floor.
    """
    design = [_synthetic_candidate(f"pos_hi_{i}", 0.9, True, False) for i in range(14)]
    design += [_synthetic_candidate(f"pos_lo_{i}", 0.3, True, False) for i in range(6)]
    design += [_synthetic_candidate(f"neg_lo_{i}", 0.1, False, False) for i in range(19)]
    design.append(_synthetic_candidate("neg_hi_family", 0.5, False, True))
    return design


def test_01_gate_refuses_over_separation(cfg: Config, design, graph, costs) -> None:
    """The difficulty gate must refuse an over-separated design as a
    property of the gate itself, not as a fact that happens to be true of
    one hyperparameter configuration on one run's population.

    Previously this asserted that G3_unregularised (deliberately overfit --
    2 layers, hidden dim 32, no weight decay) gets refused, with a
    conditional escape if it did not (provided some other candidate was
    refused instead). At the population Task 4 added, NEITHER G3 nor any
    other GraphSAGE candidate over-separates any more -- G3's own
    positives_below_max_negative sits at 0.4783, just above the 0.45 floor
    -- because a larger design-split negative pool mechanically raises the
    single highest negative score (extreme-value statistics), independent
    of whether the scorer is actually any good. That is a fact about
    population scale, not a regression in the gate: test_ml.py check 01
    still refuses XGBoost's X4_unregularised on this same population, so the
    gate mechanism demonstrably retains teeth. Testing the gate directly
    against a hand-built over-separated set (see `_degenerate_design`)
    checks the property the gate exists to guarantee without depending on
    whether this run's population happens to make any real candidate trip it.
    """
    synthetic = _degenerate_design()
    synthetic_costs = derive_costs(synthetic)
    try:
        gated_expected_loss(cfg, synthetic, 0.5, synthetic_costs)
    except DifficultyGateFailure:
        pass
    else:
        raise AssertionError(
            "gated_expected_loss() accepted a hand-built, over-separated "
            "candidate set -- the difficulty gate has stopped refusing "
            "over-separation entirely"
        )

    # G3_unregularised stays in CANDIDATES as a realistic stress case and is
    # reported informationally below -- nothing is asserted on its outcome,
    # since whether one hyperparameter configuration over-separates is a
    # fact about this run's population, not about the gate (see docstring).
    result = select_gnn_model(cfg, design, graph, costs)
    row = next(r for r in result["candidates"] if r["policy"] == "G3_unregularised")
    g3_status = (f"refused ({row['refused_by']})" if not row["feasible"]
                else f"feasible (pbmn {row['positives_below_max_negative']} -- "
                     "does not over-separate at this population)")

    check("01 gated_expected_loss() refuses a hand-built over-separated "
          f"candidate set (DifficultyGateFailure); G3_unregularised {g3_status}, "
          "reported informationally")


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
        test_01_gate_refuses_over_separation(cfg, design, graph, costs)
        test_02_select_asserts_design_only(cfg, cands, graph, costs)
        test_03_frozen_guard(cfg, cands, graph, tmp)
        test_04_determinism(cfg, cands, graph)
        print(f"\n{len(PASSED)}/4 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
