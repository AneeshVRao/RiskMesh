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
2. **Gate evaluation.** The train-fit model scores **validation** components
   only — out-of-sample, the rows it was not fit on. `panel_verdict()` and the
   two difficulty bounds are computed on this validation-only view, never
   mixed with train's in-sample predictions. This is a deliberate departure
   from the weight search's own gate, which evaluates on train+validation
   combined — that is safe for a hand-set weight vector, which is not "fit"
   on anything and applies the identical formula to every split alike. It is
   not safe here: a boosted model's in-sample predictions on the rows it was
   trained on are biased toward separation regardless of whether the model
   generalises, and mixing them into the gate's input would let every
   candidate look like it had eroded the benchmark's difficulty even when it
   had not. Evaluating the gate exclusively on out-of-sample validation scores
   is what keeps the gate measuring the model's actual generalisation, which
   is the property worth gating on.
3. **Threshold / objective.** Expected loss is minimised by sweeping
   thresholds 0.00–1.00 in 0.01 steps, scored on that same **validation-only**
   out-of-sample view, via `costmodel.expected_loss()` through
   `costmodel.gated_expected_loss()`, reusing `costmodel.derive_costs()`'s
   already-derived costs (computed on train+validation, unchanged) without
   re-deriving them. This is the identical sweep-and-minimise shape
   `select_weights()` uses; `evaluate.select_threshold()` selects by F1, a
   different metric, so it is not called for this step — the objective stated
   by this protocol is expected loss, not F1, and reusing a different
   function's F1 sweep instead of the weight search's own sweep-and-minimise
   loop would silently swap the selection metric.
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
   b. Score **validation** components only with that fit (out-of-sample),
      replacing `.score` via `dataclasses.replace(c, score=pred)`. Train
      rows' in-sample predictions are not computed for this step and never
      enter the gate.
   c. Run the non-triviality panel and the two difficulty gates on that
      validation-only view (§3, §4).
   d. If any gate fails: record which exception fired and the failing
      checks. **No expected loss.** Next candidate.
   e. Otherwise sweep thresholds 0.00–1.00 in 0.01 steps on that same
      validation-only view and take the minimum expected loss.
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

## 8. Outcome — no candidate feasible, no held-out read taken

Record: `experiments/xgboost_policy.json` (byte-copied to
`out/xgboost_policy.json`). Installed `xgboost.__version__` **3.4.1**. Costs
re-derived on the current benchmark (identical derivation to
`weight_search_protocol.md` §4/§8, same `derive_costs()` call, same design
split): `C_review` 500.00, `C_fn` 68,399.84, `C_fp` 398.43, ratio 171.7:1.
Config fingerprint `c3ee14627c2c2ce2`, seed 20260824.

**All four candidates were refused. None reached the threshold sweep or an
expected-loss figure.**

| policy | panel | pbmn | hard-neg | distinct predictions | feasible | reason |
|---|---|---|---|---|---|---|
| **X1_shallow** | FAIL | 0.0000 | 8 | **1** | no | degenerate constant predictor |
| **X2_moderate** | FAIL | 0.0000 | 8 | **1** | no | degenerate constant predictor |
| **X3_stumps** | FAIL | 0.0000 | 8 | **1** | no | degenerate constant predictor |
| **X4_unregularised** | FAIL | 0.1250 | 1 | 23 | no | genuine over-separation |

**Two distinct failure mechanisms produced the same refusal, and they are not
the same finding.**

**X1, X2 and X3 never split at all.** Inspecting each fit's booster
(`get_booster().trees_to_dataframe()`) shows every one of their boosted trees
is a single unsplit leaf -- `min_child_weight` (5, 3, and 3 respectively),
combined with `subsample` and this benchmark's ~30-row training split (8
positive, 30 negative on train, further subsampled), means no candidate split
anywhere ever leaves both children with enough weight to clear the bound. The
model degenerates to one constant prediction for every validation component
(`n_unique_validation_predictions == 1`, confirmed directly against the
fitted boosters, not inferred from the gate output). Re-fitting each with
`min_child_weight` removed (all other hyperparameters unchanged) confirms
this is exactly the mechanism: splits appear immediately once the bound is
relaxed.

A constant score fails `positives_below_max_negative` for a reason unrelated
to the one that check exists to catch: with every prediction tied, **zero**
positive scores are *strictly less than* the (also tied) top negative score,
so the computed fraction reads 0.0000 -- identical to what genuine
over-separation would produce, for the opposite underlying reason (no
discrimination at all, rather than too much of it). This is not a flaw in the
gate found after the fact and patched around; it is reported here exactly as
observed, because the gate's job is to refuse a candidate that cannot be
trusted to report an honest expected loss, and a constant classifier
qualifies on that description regardless of why it is constant. The
`n_unique_validation_predictions` diagnostic is recorded in the frozen JSON
precisely so this distinction is visible without re-deriving it from the
booster later.

**This is a sharper version of the L2 risk than anticipated, in the opposite
direction from the one `xgboost_protocol.md` §2/§3 named going in.** The
protocol worried about a model with excess capacity finding an easy
separation; what three of four candidates actually demonstrate is that
heavy regularisation, calibrated for "a ~30-row training set" in the abstract,
can be strict enough for *this* concrete 38-row split that the model never
fits any structure at all. Both directions -- too much separation and too
little discrimination -- land on the identical numeric gate value here, which
is itself worth recording: `positives_below_max_negative` cannot, by
construction, distinguish "benchmark made trivially easy" from "model learned
nothing," and a future reader of this number alone should not assume the
former without checking `n_unique_validation_predictions` alongside it.

**X4_unregularised behaved exactly as predicted in §2.** It does split (171
non-leaf nodes across its 300 trees) and reaches 23 distinct predictions on
validation, but drives `positives_below_max_negative` to 0.1250 -- below even
the base non-triviality panel's own 0.20 bound, not only the tightened 0.45
difficulty gate -- and `hard_negatives_inside_positive_range` to 1. This is
the genuine over-separation mechanism the deliberately-overfit candidate was
included to demonstrate, and the gate refuses it exactly as expected: **the
gate fires against XGBoost, not only against hand-picked weight vectors.**

**Winner: none. No candidate is feasible.** Per §6, stated before this run:
*"If no candidate is feasible ... that is the finding, reported as such --
not a reason to add a fifth candidate or loosen a gate."* No fifth candidate
was added, no bound was loosened, and no candidate's hyperparameters were
adjusted after this result was seen.

### Step 8 — the held-out read that was not taken

`evaluate_frozen_ml_policy()` was called against the frozen record above and
raised `MLPolicyNotFrozen`, by design (§4 of `riskmesh/ml.py`'s docstring for
that function): the record exists but names no winner, so there is no
hyperparameter configuration to refit on train+validation and no model the
protocol permits scoring the test split with. **The test split was not read.**
This is the correct behaviour, not a gap: reading held-out data against an
ungated model would produce a number with no protocol backing it, exactly the
failure mode `PolicyNotFrozen` / `MLPolicyNotFrozen` exist to prevent
structurally rather than by convention.

### Verdict against the Tier 1 baseline

**XGBoost does not beat Tier 1 in this experiment, because no XGBoost
candidate reached a held-out reading at all.** Tier 1's frozen numbers stand
unchanged: F1 **0.7778**, expected loss **74,595.13**, at threshold 0.18, on
31 test components (`weight_search_protocol.md` §8). There is no XGBoost F1
or expected loss to compare against them -- not "an unfavourable one," none.
This is reported as the finding it is: over four pre-declared, small,
regularised-for-a-small-dataset hyperparameter configurations, the
non-triviality/difficulty gates -- reused completely unchanged from the
linear weight search -- refused every one, three for producing no usable
discrimination at all and one for producing too much. The honest conclusion
is that this candidate list, on this benchmark's ~69 design components (16
positive), does not clear the bar this project already holds the linear
scorer to, and no attempt was made to lower that bar to manufacture a result.

**No further read is permitted under this record.** Any future XGBoost
comparison -- a different feature set, a different candidate list, k-fold
resampling of the tiny training set -- needs its own frozen protocol.
