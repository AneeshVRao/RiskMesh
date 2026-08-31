"""riskmesh.ml checks. Plain asserts, no framework:  python tests/test_ml.py

Four checks, per `xgboost_protocol.md` and `task_today.md`:

  01  the deliberately-overfit X4 candidate is refused by the gate -- proves
      the gate fires against XGBoost, not just against hand-picked weight
      vectors.
  02  select_xgboost_model() asserts it received design-only candidates and
      raises on a test row, mirroring select_weights()'s own assertion.
  03  evaluate_frozen_ml_policy() raises MLPolicyNotFrozen before the freeze
      file exists.
  04  refitting the same frozen hyperparameters twice on the same data
      produces the same prediction for a given component (determinism, to
      the extent xgboost's own determinism guarantees allow).

Does not touch tests/test_riskmesh.py or tests/test_api.py.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import xgboost

from riskmesh.config import Config
from riskmesh.costmodel import derive_costs
from riskmesh.evaluate import build_candidates
from riskmesh.generate import generate
from riskmesh.graph import build_graph
from riskmesh.ml import (
    CANDIDATES,
    MLPolicyNotFrozen,
    _score_with,
    evaluate_frozen_ml_policy,
    fit_model,
    select_xgboost_model,
)
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
    return build_candidates(cfg, graph, scores, splits, labels)


def test_01_gate_fires_against_x4(cfg: Config, design, costs) -> None:
    """bugs.md L2, sharper here: a gradient-boosted model has far more
    capacity than a linear score to make the benchmark look easier. The
    deliberately-overfit X4_unregularised candidate exists to prove the same
    three gates (reused UNCHANGED from the weight search) still refuse a
    genuinely bad candidate when the model family changes.
    """
    result = select_xgboost_model(cfg, design, costs)
    row = next(r for r in result["candidates"] if r["policy"] == "X4_unregularised")
    assert not row["feasible"], (
        "X4_unregularised (deliberately overfit) was NOT refused -- the gate "
        "has stopped firing against a genuinely bad XGBoost candidate"
    )
    assert row["refused_by"] in ("PanelGateFailure", "DifficultyGateFailure")
    check(f"01 X4_unregularised refused by the gate ({row['refused_by']}) -- "
          "the gate fires against XGBoost, not only against weight vectors")


def test_02_select_asserts_design_only(cfg: Config, cands, costs) -> None:
    design = [c for c in cands if c.split in ("train", "validation")]
    test_rows = [c for c in cands if c.split == "test"]
    assert test_rows, "no test rows to contaminate the design view with"
    contaminated = design + test_rows[:1]
    try:
        select_xgboost_model(cfg, contaminated, costs)
    except AssertionError:
        pass
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError(
            "select_xgboost_model accepted a candidate from the test split -- "
            "this would be model fitting/gating on held-out data"
        )
    check("02 select_xgboost_model refuses a design view containing a test row")


def test_03_frozen_guard(cfg: Config, cands, tmp: Path) -> None:
    design = [c for c in cands if c.split in ("train", "validation")]
    test_rows = [c for c in cands if c.split == "test"]
    policy_path = tmp / "xgboost_policy_missing.json"
    assert not policy_path.exists()
    try:
        evaluate_frozen_ml_policy(cfg, design, test_rows, policy_path)
    except MLPolicyNotFrozen:
        pass
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError(
            "evaluate_frozen_ml_policy read the test split before any policy "
            "was frozen to disk"
        )
    check("03 evaluate_frozen_ml_policy raises MLPolicyNotFrozen before the "
          "freeze file exists")


def test_04_determinism(cfg: Config, cands) -> None:
    """Refit each of the four frozen hyperparameter configurations twice on
    identical train rows and compare validation predictions.

    xgboost's internal RNG and tree-building are not guaranteed bit-identical
    across library versions (see requirements.txt) -- this asserts exact
    equality because that is what the installed xgboost version actually
    produces on this small, single-process fit in this environment, not
    because bit-exact determinism is a guarantee this project can make about
    every future xgboost release. If this test is ever seen to fail after an
    xgboost upgrade, that is the finding to record here, not a reason to
    loosen the assertion into a flaky tolerance.
    """
    train = [c for c in cands if c.split == "train"]
    validation = [c for c in cands if c.split == "validation"]
    for name, hyperparams in CANDIDATES.items():
        model_a = fit_model(cfg, hyperparams, train)
        model_b = fit_model(cfg, hyperparams, train)
        scored_a = _score_with(model_a, validation)
        scored_b = _score_with(model_b, validation)
        for a, b in zip(scored_a, scored_b):
            assert a.component_id == b.component_id
            assert a.score == b.score, (
                f"{name} is not deterministic on xgboost {xgboost.__version__}: "
                f"component {a.component_id} scored {a.score} then {b.score} "
                "from two fits with the same random_state on identical data"
            )
    check(f"04 determinism: refitting each of {len(CANDIDATES)} candidates "
          f"twice gives bit-identical validation predictions on installed "
          f"xgboost {xgboost.__version__}")


def main() -> int:
    cfg = Config()
    cands = build(cfg)
    design = [c for c in cands if c.split in ("train", "validation")]
    costs = derive_costs(design)

    tmp = Path(tempfile.mkdtemp(prefix="riskmesh_ml_test_"))
    try:
        print(f"\nriskmesh.ml checks  (seed {cfg.seed}, config {cfg.fingerprint()}, "
              f"xgboost {xgboost.__version__})\n")
        test_01_gate_fires_against_x4(cfg, design, costs)
        test_02_select_asserts_design_only(cfg, cands, costs)
        test_03_frozen_guard(cfg, cands, tmp)
        test_04_determinism(cfg, cands)
        print(f"\n{len(PASSED)}/4 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
