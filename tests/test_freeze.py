"""riskmesh.freeze checks (weights stage only -- no xgboost/torch at import
time, per G7). Plain asserts, no framework:  python tests/test_freeze.py

One smoke check: `freeze_weights()` writes to a scratch path (never the real
`experiments/weight_policy.json`) and its result is compared against the
committed record on disk -- the smallest thing that fails if freeze.py's
reconstruction of select_weights()'s output (built candidates, gates,
sensitivity sweep) ever drifts from what Task 1 verified was byte-identical.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riskmesh.freeze import EXPERIMENTS, freeze_weights

PASSED: list[str] = []


def check(name: str) -> None:
    PASSED.append(name)
    print(f"  ok   {name}")


def test_01_weights_matches_committed_record(tmp: Path) -> None:
    committed = json.loads(
        (EXPERIMENTS / "weight_policy.json").read_text(encoding="utf-8")
    )
    regenerated = freeze_weights(path=tmp / "weight_policy.json")

    assert regenerated["winner"] == committed["winner"], (
        f"freeze_weights() winner {regenerated['winner']!r} != committed "
        f"record's {committed['winner']!r}"
    )
    assert (regenerated["sensitivity"]["distinct_winners"]
            == committed["sensitivity"]["distinct_winners"]), (
        "freeze_weights() sensitivity.distinct_winners "
        f"{regenerated['sensitivity']['distinct_winners']!r} != committed "
        f"record's {committed['sensitivity']['distinct_winners']!r}"
    )
    assert regenerated["winner_threshold"] == committed["winner_threshold"], (
        f"freeze_weights() winner_threshold {regenerated['winner_threshold']!r} "
        f"!= committed record's {committed['winner_threshold']!r}"
    )
    assert regenerated["winner_expected_loss"] == committed["winner_expected_loss"], (
        "freeze_weights() winner_expected_loss "
        f"{regenerated['winner_expected_loss']!r} != committed record's "
        f"{committed['winner_expected_loss']!r}"
    )
    check("01 freeze_weights() reproduces the committed record's winner, "
          "winner_threshold, winner_expected_loss, and "
          "sensitivity.distinct_winners")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="riskmesh_freeze_test_"))
    try:
        print("\nriskmesh.freeze checks (weights stage)\n")
        test_01_weights_matches_committed_record(tmp)
        print(f"\n{len(PASSED)}/1 checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
