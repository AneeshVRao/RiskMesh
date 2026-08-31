# XGBoost-search protocol — frozen before any candidate is scored

**Status: WRITTEN, NOT YET RUN.** This document is committed before
`select_xgboost_model()` is run against real data, and before any candidate's
score is looked at — exactly the discipline `weight_search_protocol.md`
followed. §8 (results) is appended only after the freeze in
`experiments/xgboost_policy.json` exists and the single held-out read has been
taken through `evaluate_frozen_ml_policy()`.

Code: `riskmesh/ml.py`. Evidence for why the gate exists: `bugs.md` L2, and
`implementation_plan.md`'s "Why abstention comes before XGBoost", which names
this exact risk before this phase started: *"A gradient-boosted model has far
more capacity [than a linear score] to find that kind of solution [an easier
benchmark], and it will find it preferentially, because it is the cheapest way
to improve the objective."*

---

## 1. What is being selected, and what is not

**Selected:** one XGBoost hyperparameter configuration, from a fixed list of
four candidates, by minimum expected loss on validation — the same objective
`weight_search_protocol.md` used for weight vectors.

**Not selected here:** the generator, any signal definition, the ground-truth
rule, the split, or the feature set. The input space is fixed to the linear
scorer's own 8 normalised signals (`Candidate.signals`, `riskmesh.config.SIGNALS`
order) with no additional engineered features (size, exposure, txn count) —
this isolates the comparison to "linear combination vs. gradient-boosted trees
over the same evidence," which is the only honest comparison to report. A
richer feature set is a separate, later decision.

**No hyperparameter search.** Four named configurations, not a grid or an
optimiser, for the same reason five weight vectors were used rather than a
continuous search: a search over XGBoost's hyperparameter space against ~30
training rows would fit noise, and there would be no honest way to report how
many configurations were tried. Four pre-declared configurations can be
reported in full.

---

## 2. The candidate list

Fixed in advance. No candidate may be added after any result is seen.

| | policy | hyperparameters | why it is on the list |
|---|---|---|---|
| **X1** | `X1_shallow` | `n_estimators=30, max_depth=2, learning_rate=0.1, min_child_weight=5, subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0` | conservative, heavily regularised for a ~30-row training set |
| **X2** | `X2_moderate` | `n_estimators=60, max_depth=3, learning_rate=0.1, min_child_weight=3, subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0` | a step up in capacity |
| **X3** | `X3_stumps` | `n_estimators=15, max_depth=1, learning_rate=0.2, min_child_weight=3, subsample=1.0, colsample_bytree=1.0, reg_lambda=1.0` | depth-1 boosted stumps — an additive model over individual features, the closest capacity-match to the linear scorer, included specifically so "XGBoost beats linear" is not confounded with "XGBoost has vastly more capacity" |
| **X4** | `X4_unregularised` | `n_estimators=300, max_depth=6, learning_rate=0.3, min_child_weight=1, subsample=1.0, colsample_bytree=1.0, reg_lambda=0.0` | deliberately overfit-prone. **Expected to be refused by the gate** — included the same way `D_drop_flagged` was in the weight search, because a protocol whose gate never fires on a genuinely bad candidate has not been shown to work |

All four use `xgboost.XGBClassifier(objective="binary:logistic",
eval_metric="logloss", random_state=cfg.seed, **hyperparameters)`.

X4 is deliberately included as a candidate that should fail. **A protocol
whose gate never fires has not been shown to work.**

---

## 3. The gate — reused unchanged from the weight search

A candidate that fails **any of three** gates **is not a candidate**. It does
not receive an expected-loss figure that is later discarded; there is no
figure.

| gate | bound | enforced by |
|---|---|---|
| non-triviality panel | verdict `PASS` | `PanelGateFailure` |
| hard negatives inside the positive range | `>= 4` | `DifficultyGateFailure` |
| positives below the top negative | `>= 0.45` | `DifficultyGateFailure` |

These are `costmodel.MIN_HARD_NEGATIVES_IN_RANGE` and
`costmodel.MIN_POSITIVES_BELOW_MAX_NEGATIVE`, imported into `riskmesh/ml.py`
and used through `costmodel.gated_expected_loss()` and `costmodel.panel_verdict()`
directly — **not redeclared**. The whole point of this phase is that XGBoost's
candidates are held to the identical bar the weight vectors were; a new bound
tuned for the new model type would defeat the purpose of having a gate at all.

**Why this matters more here than in the linear search.** A gradient-boosted
model has far more capacity than a 7-8-term linear score to find a way to make
the *benchmark* look easier rather than to genuinely discriminate rings from
families, and with ~16 positive design components it can do this by fitting
noise as readily as by fitting signal. `bugs.md` L2 already showed this
mechanism firing on a linear scorer twice; a tree ensemble that can carve
arbitrary axis-aligned regions is a strictly easier way to find it. The gate
is therefore enforced structurally, exactly as before: `gated_expected_loss()`
raises `PanelGateFailure` or `DifficultyGateFailure` instead of returning a
number, and the search records the refusal and moves on.

**Two further structural guarantees, mirroring `select_weights()` /
`select_threshold()`:**

* `select_xgboost_model()` takes design candidates as its whole input and
  asserts it received nothing else.
* `evaluate_frozen_ml_policy()` raises `MLPolicyNotFrozen` unless the winning
  configuration is already written to disk.

---

## 4. Fitting discipline — train vs. validation vs. design vs. test

Four splits of the same design/test distinction, stated precisely because a
gradient-boosted model gives leakage more places to hide than a weight vector
does:

1. **Model selection (fitting).** Each of the four candidates is fit on
   **TRAIN split components only** — not train+validation. This mirrors the
   existing single train→validation flow used everywhere else in this
   codebase (`select_threshold`, `select_weights`) rather than introducing
   k-fold cross-validation, which would be a new pattern this project does
   not otherwise use.
2. **Gate evaluation.** The train-fit model scores every **design**
   (train+validation) component out-of-sample for the rows it was not fit on
   (validation) and in-sample for the rows it was (train). `panel_verdict()`
   and the two difficulty bounds are computed on this design view, exactly as
   the weight search computes them on train+validation.
3. **Threshold / objective.** Expected loss is minimised by sweeping
   thresholds 0.00–1.00 in 0.01 steps, scored on **validation only** — the
   out-of-sample rows for the selection fit — via `costmodel.expected_loss()`
   through `costmodel.gated_expected_loss(..., score_on=validation)`, reusing
   `costmodel.derive_costs()`'s already-derived costs without re-deriving
   them. This is the identical sweep-and-minimise shape `select_weights()`
   uses; `evaluate.select_threshold()` selects by F1, a different metric, so
   it is not called for this step — the objective stated by this protocol is
   expected loss, not F1, and reusing a different function's F1 sweep instead
   of the weight search's own sweep-and-minimise loop would silently swap the
   selection metric.
4. **Refit for the final read.** Once a candidate is selected, its SAME
   hyperparameter configuration is refit on **train+validation combined** (all
   design data) before it is used to score the held-out test split. This is
   standard practice and does not leak: design is disjoint from test
   throughout, and the refit still never sees a test row's features or label.
   The model used to produce the selection numbers in §8's candidate table
   (train-fit) is therefore **not** the same model object used for the §8
   held-out read (train+validation-fit) — both are the same hyperparameters,
   fit on different, always-design-only, data.

---

## 5. Procedure

1. Regenerate `out/` (`rm -rf out && python -m riskmesh`) and confirm the
   Tier 1 baseline (F1 0.7778, expected loss 74,595.13, threshold 0.18) is
   still current, reading it from `out/eval_report.json` /
   `out/weight_policy.json` rather than trusting a quoted number.
2. Build the standard candidate set once (generator untouched, current
   `A_baseline` weights — the linear scorer's own `.score` field is discarded
   for this phase; only `Candidate.signals` is read).
3. Derive costs from **train+validation** (`costmodel.derive_costs`), reused
   unchanged.
4. For each of the four candidates, in the declared order:
   a. Fit `XGBClassifier(**hyperparameters, objective="binary:logistic",
      eval_metric="logloss", random_state=cfg.seed)` on **train** components'
      8 signals.
   b. Score every **design** component with that fit, replacing `.score` via
      `dataclasses.replace(c, score=pred)`.
   c. Run the non-triviality panel and the two difficulty gates on the
      **design** view (§3).
   d. If any gate fails: record which exception fired and the failing
      checks. **No expected loss.** Next candidate.
   e. Otherwise sweep thresholds 0.00–1.00 in 0.01 steps on the **validation**
      subset of the design view and take the minimum expected loss.
5. Select the candidate with the lowest validation expected loss among
   feasible candidates. Ties break toward the earlier-declared (and by
   construction more conservative) candidate — X1 before X2 before X3 before
   X4 — never toward the more complex configuration. If no candidate is
   feasible, that is the finding: no fifth candidate is added and no gate is
   loosened.
6. Refit the winning hyperparameter configuration on **train+validation
   combined** (§4.4).
7. Write the winner, its threshold, its validation expected loss, its panel
   row, the full four-candidate table, and the installed `xgboost.__version__`
   to `experiments/xgboost_policy.json`. **Freeze.** Copy byte-identically to
   `out/xgboost_policy.json`, mirroring `weight_policy.json`'s pattern in
   `__main__.py`.
8. Read the held-out split **once**, through `evaluate_frozen_ml_policy()`
   (using the train+validation refit from step 6), and report precision,
   recall, F1, FPR, ring recovery, expected loss, review rate — the same set
   `weight_search_protocol.md` §5 step 6 reports.
9. No second read. If the held-out result disappoints, that is the result.

---

## 6. What "beat the Tier 1 baseline" means

Stated up front, before any candidate's held-out number is known: **beating
Tier 1 means the selected candidate's held-out F1 or held-out expected loss is
at least as good as Tier 1's frozen 0.7778 F1 / 74,595.13 expected loss** (F1
higher is better; expected loss lower is better). Both are reported
regardless of which, if either, wins — this project's convention of reporting
honestly whichever way it lands, not the convention of quoting the flattering
half.

**If no candidate is feasible, or the best feasible candidate does not beat
Tier 1, that is the finding, reported as such.** It is not a reason to add a
fifth candidate, loosen a gate, or re-derive costs until the answer looks
better. A held-out result that does not improve on the linear scorer is
exactly as reportable as one that does — this project has already reported an
19x validation-to-test gap (`weight_search_protocol.md` §8) and a
flag-everything comparison the winner lost (same section) without adjusting
anything after the fact to make either look better.

---

## 7. What would invalidate this protocol

Stated so it is falsifiable:

* Any candidate added, removed, or redefined after a result is seen.
* Any feature added beyond the 8 existing signals, after a result is seen.
* Any cost input changed after seeing which configuration wins.
* Any expected-loss number produced for a gate-failing candidate.
* More than one held-out read.
* The gate's bounds changed after step 4 (§5) begins — including changing them
  "for XGBoost specifically" rather than for the whole codebase.
* The selection fit (train-only) and the final-read fit (train+validation)
  being conflated — i.e., a candidate's §8 table row using a model that ever
  saw validation features during the fit that produced that row's numbers.

If any of these happens, the protocol is void and the selection is re-run from
a new frozen record.

---

## 8. Outcome

*(Appended after the freeze and the single held-out read — not written until
then.)*
