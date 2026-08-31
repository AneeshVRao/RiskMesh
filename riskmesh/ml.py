"""XGBoost scorer over the linear scorer's own 8 signals, gated identically.

The protocol is described in `xgboost_protocol.md`, written and committed
before this module ran against real data, exactly as `weight_search_protocol.md`
preceded `costmodel.py`. This module mirrors `costmodel.py`'s shape closely --
same author, same discipline, different model family.

Why the gate matters more here than in the linear weight search:
`implementation_plan.md`'s "Why abstention comes before XGBoost" already flags
this before this phase started. A gradient-boosted model has far more capacity
than a 7-8-term linear score to find a way to make the *benchmark* look easier
rather than to genuinely discriminate rings from families, and with ~16
positive design components it can do this by fitting noise as readily as by
fitting signal. `bugs.md` L2 already showed this failure mode on a linear
scorer twice; a tree ensemble that can carve arbitrary axis-aligned regions is
a strictly easier way to find it.

So this module reuses `costmodel.panel_verdict()` and its two difficulty
bounds UNCHANGED -- no new, more permissive bar for XGBoost's candidates.
`costmodel.gated_expected_loss()` still raises `PanelGateFailure` or
`DifficultyGateFailure` instead of returning a number; an infeasible candidate
here gets no F1, exactly as an infeasible weight vector gets none.

Two further guarantees, both structural rather than remembered:

* `select_xgboost_model()` takes design candidates and asserts it received
  nothing else, exactly as `select_weights()` does. Fitting for selection uses
  TRAIN rows only; the threshold sweep inside it uses VALIDATION rows only.
* `evaluate_frozen_ml_policy()` refuses to touch the test split until the
  winning configuration has been written to disk, raising `MLPolicyNotFrozen`.

Reproducibility note (see `requirements.txt`): xgboost's own internal RNG and
tree-building are not guaranteed bit-identical across library versions, the
same way `config.py` scopes Python's own `random` module to "one interpreter
version". `xgboost.__version__` is recorded in every frozen record this module
produces, the same way `sys.version` already is everywhere else.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import xgboost

from .config import SIGNALS, Config
from .costmodel import (
    DESIGN_SPLITS,
    MIN_HARD_NEGATIVES_IN_RANGE,
    MIN_POSITIVES_BELOW_MAX_NEGATIVE,
    PanelGateFailure,
    gated_expected_loss,
    panel_verdict,
)
from .evaluate import Candidate

DESIGN_SPLIT = "validation"
FIT_SPLIT = "train"


class MLPolicyNotFrozen(AssertionError):
    """Raised when the held-out split is read before an ML policy is on disk."""


# --------------------------------------------------------------------------
# features -- the linear scorer's own 8 signals, nothing invented
# --------------------------------------------------------------------------


def features(cands: list[Candidate]) -> tuple[list[str], list[list[float]]]:
    """Each candidate's 8 normalised signal values, in `SIGNALS` order.

    Same evidence the linear scorer uses (`Candidate.signals`, computed with
    no label access), nothing new invented -- no size, exposure, or txn count.
    Keeping the input space identical to the linear scorer's isolates the
    comparison to "linear combination vs. gradient-boosted trees over the same
    evidence," which is the honest comparison to report.
    """
    names = list(SIGNALS)
    x = [[c.signals[name] for name in names] for c in cands]
    return names, x


# --------------------------------------------------------------------------
# candidates -- a fixed list, declared in advance, with no search space
# --------------------------------------------------------------------------

CANDIDATES: dict[str, dict[str, Any]] = {
    "X1_shallow": dict(
        n_estimators=30, max_depth=2, learning_rate=0.1, min_child_weight=5,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
    ),
    "X2_moderate": dict(
        n_estimators=60, max_depth=3, learning_rate=0.1, min_child_weight=3,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
    ),
    "X3_stumps": dict(
        n_estimators=15, max_depth=1, learning_rate=0.2, min_child_weight=3,
        subsample=1.0, colsample_bytree=1.0, reg_lambda=1.0,
    ),
    "X4_unregularised": dict(
        n_estimators=300, max_depth=6, learning_rate=0.3, min_child_weight=1,
        subsample=1.0, colsample_bytree=1.0, reg_lambda=0.0,
    ),
}


def _model(cfg: Config, hyperparams: dict[str, Any]) -> xgboost.XGBClassifier:
    return xgboost.XGBClassifier(
        objective="binary:logistic", eval_metric="logloss",
        random_state=cfg.seed, **hyperparams,
    )


def fit_model(cfg: Config, hyperparams: dict[str, Any],
              fit_on: list[Candidate]) -> xgboost.XGBClassifier:
    """Fit one hyperparameter configuration on exactly the given rows.

    A thin wrapper so both the selection fit (train only) and the final refit
    (train+validation) go through one code path -- see §4 of
    `xgboost_protocol.md` for why they must never be the same call.
    """
    _, x = features(fit_on)
    y = [int(c.is_positive) for c in fit_on]
    model = _model(cfg, hyperparams)
    model.fit(x, y)
    return model


def _score_with(model: xgboost.XGBClassifier,
                cands: list[Candidate]) -> list[Candidate]:
    """Replace `.score` with the model's predicted probability of positive."""
    _, x = features(cands)
    preds = model.predict_proba(x)[:, 1]
    return [replace(c, score=float(p)) for c, p in zip(cands, preds)]


# --------------------------------------------------------------------------
# protocol
# --------------------------------------------------------------------------


def select_xgboost_model(cfg: Config, design: list[Candidate],
                         costs: dict[str, Any]) -> dict[str, Any]:
    """Score every candidate configuration behind all three gates.

    Takes design candidates as its whole input and asserts it received
    nothing else, in the same shape as `select_weights()`. Each candidate is
    FIT on train rows only (never validation, never test) and then scored
    OUT-OF-SAMPLE on validation rows only -- never on the train rows it was
    fit on -- for both the feasibility gates and the threshold sweep. In-sample
    train predictions are never mixed into either: a boosted model's in-sample
    scores are biased separated (it has seen those labels), and mixing them
    into the design view the gate reads would make every candidate look like
    it had eroded the benchmark's difficulty regardless of whether it
    generalises, which defeats the point of gating on out-of-sample behaviour
    at all. No path through this function reaches the test split, and no fit
    inside it ever sees a validation or test label.

    Feasibility is checked before expected loss, not alongside it: an
    infeasible candidate never receives a number to be compared against.
    """
    assert all(c.split in DESIGN_SPLITS for c in design), (
        "select_xgboost_model received non-design candidates -- "
        "this would be model fitting on held-out data"
    )
    train = [c for c in design if c.split == FIT_SPLIT]
    assert train, "no train-split candidates to fit on"

    results: list[dict[str, Any]] = []
    for name, hyperparams in CANDIDATES.items():
        model = fit_model(cfg, hyperparams, train)
        validation = _score_with(
            model, [c for c in design if c.split == DESIGN_SPLIT]
        )
        v = panel_verdict(cfg, validation)
        n_unique_preds = len({round(c.score, 6) for c in validation})
        row: dict[str, Any] = {
            "policy": name,
            "hyperparameters": dict(hyperparams),
            "panel_verdict": v["verdict"],
            "panel_failing_checks": v["failing_checks"],
            "positives_below_max_negative": v["positives_below_max_negative"],
            "hard_negatives_inside_positive_range":
                v["hard_negatives_inside_positive_range"],
            # Diagnostic, not a gate: at this candidate's regularisation and
            # this ~30-row training set, a model can degenerate to a SINGLE
            # constant prediction (every tree fit is leaf-only, no split ever
            # clears min_child_weight). A constant score also reads
            # positives_below_max_negative == 0.0 -- ties are not "below" --
            # which is the SAME number over-separation produces, for the
            # opposite reason (no discrimination at all, not too much of it).
            # This field makes that distinction visible in the record rather
            # than leaving both failure modes to look identical.
            "n_unique_validation_predictions": n_unique_preds,
        }
        best: dict[str, Any] | None = None
        try:
            for i in range(101):
                t = i / 100.0
                loss = gated_expected_loss(cfg, validation, t, costs)
                if best is None or loss["expected_loss"] < best["expected_loss"]:
                    best = {**loss, "threshold": t}
        except PanelGateFailure as exc:
            row["feasible"] = False
            row["refused_by"] = type(exc).__name__
            row["reason"] = str(exc)
        else:
            assert best is not None
            row["feasible"] = True
            row.update(best)
        results.append(row)

    feasible = [r for r in results if r["feasible"]]
    # Ties break toward the earlier-declared (and by construction more
    # conservative) candidate -- X1 before X2 before X3 before X4 -- never
    # toward the more complex configuration. dict insertion order gives us
    # this for free via a stable min() over `results` in declared order.
    order = {name: i for i, name in enumerate(CANDIDATES)}
    winner = min(
        feasible, key=lambda r: (r["expected_loss"], order[r["policy"]]),
    ) if feasible else None

    return {
        "protocol": "xgboost_protocol.md",
        "xgboost_version": xgboost.__version__,
        "gates": {
            "panel_verdict": "PASS",
            "hard_negatives_inside_positive_range":
                f">= {MIN_HARD_NEGATIVES_IN_RANGE}",
            "positives_below_max_negative":
                f">= {MIN_POSITIVES_BELOW_MAX_NEGATIVE}",
            "declared": (
                "Reused UNCHANGED from costmodel.py / weight_search_protocol.md. "
                "Not redeclared for XGBoost -- the whole point of this phase is "
                "that XGBoost's candidates are held to the identical bar the "
                "weight vectors were."
            ),
            "enforcement": (
                "gated_expected_loss() raises PanelGateFailure or "
                "DifficultyGateFailure instead of returning a number. An "
                "infeasible candidate has no expected loss at all."
            ),
        },
        "costs": costs,
        "fit_on": "train only (selection); gates and threshold sweep both "
                  "computed on validation predictions only, out-of-sample "
                  "for every candidate -- train's in-sample scores are never "
                  "mixed in",
        "candidates": results,
        "feasible": [r["policy"] for r in feasible],
        "infeasible": [r["policy"] for r in results if not r["feasible"]],
        "winner": winner["policy"] if winner else None,
        "winner_hyperparameters": (
            dict(CANDIDATES[winner["policy"]]) if winner else None
        ),
        "winner_threshold": winner["threshold"] if winner else None,
        "winner_expected_loss": winner["expected_loss"] if winner else None,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }


def refit_final_model(cfg: Config, design: list[Candidate],
                      hyperparameters: dict[str, Any]) -> xgboost.XGBClassifier:
    """Refit the selected hyperparameters on ALL design data (train+validation).

    Standard practice once a configuration is chosen: the selection fit
    (train only) never saw validation, so the model that scores the held-out
    test split should use every design row available. Does not leak -- design
    is disjoint from test throughout, before and after this refit.
    """
    assert all(c.split in DESIGN_SPLITS for c in design), (
        "refit_final_model received non-design candidates"
    )
    return fit_model(cfg, hyperparameters, design)


def evaluate_frozen_ml_policy(cfg: Config, design: list[Candidate],
                              test: list[Candidate],
                              policy_path: Path) -> list[Candidate]:
    """Test rows -- available only once the winning configuration is on disk.

    Refits the frozen hyperparameters on train+validation (§4.4 of
    `xgboost_protocol.md`) and scores the test rows with that refit. The
    refit never touches a test feature or label; it is disjoint design data,
    the same guarantee `costmodel.evaluate_frozen_policy()` relies on.

    Also raises `MLPolicyNotFrozen` when the frozen record exists but names no
    winner (every candidate was refused). No candidate to refit means nothing
    the protocol permits reading the held-out split with -- see
    `xgboost_protocol.md` §6: "if no candidate is feasible ... that is the
    finding," not a reason to read the test split against an ungated model.
    """
    if not policy_path.exists():
        raise MLPolicyNotFrozen(
            f"{policy_path.name} has not been frozen. The selected XGBoost "
            "configuration, its validation expected loss and its panel "
            "verdict must be recorded before the test split is read, or the "
            "comparison is not held out."
        )
    frozen = json.loads(policy_path.read_text(encoding="utf-8"))
    if frozen.get("winner") is None:
        raise MLPolicyNotFrozen(
            f"{policy_path.name} records no feasible candidate (every "
            "candidate was refused by the gate) -- there is no winning "
            "configuration to refit, so the held-out split must not be read."
        )
    hyperparameters = frozen["winner_hyperparameters"]
    model = refit_final_model(cfg, design, hyperparameters)
    return _score_with(model, test)


def freeze_ml_policy(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
