# GraphSAGE-search protocol — frozen before any candidate is scored

**Status: WRITTEN, NOT YET RUN.** This document is committed before
`select_gnn_model()` is run against real data, and before any candidate's
score is looked at — exactly the discipline `weight_search_protocol.md` and
`xgboost_protocol.md` followed. §8 (results) is appended only after the freeze
in `experiments/graphsage_policy.json` exists and the single held-out read has
been taken through `evaluate_frozen_gnn_policy()`.

Code: `riskmesh/gnn.py`. Read this alongside `xgboost_protocol.md` and
`task_today.md` — Tier 2's XGBoost attempt found **no feasible candidate at
all** on this benchmark's ~30-row train split, and the honest expectation
going in is that a GNN, which has at least as much capacity as a small
XGBoost ensemble and typically needs *more* data to train stably rather than
less, faces the same or worse difficulty. This protocol does not lower any
bar to try to avoid that outcome.

---

## 1. What is being selected, and what is not

**Selected:** one GraphSAGE-style architecture/hyperparameter configuration,
from a fixed list of three candidates, by minimum expected loss on
validation — the same objective `weight_search_protocol.md` and
`xgboost_protocol.md` used.

**Not selected here:** the generator, any signal definition, the ground-truth
rule, the split, or the graph construction rule. The graph each candidate
trains on is fixed in advance (§2 below) and built from the same structures
`riskmesh/graph.py`'s `Component` and `__main__.py`'s `_write_graph_edges()`
already compute — not a new graph construction path, and not something this
protocol tunes.

**No hyperparameter search.** Three named configurations, not a grid or an
optimiser, for the same reason four XGBoost configurations (and five weight
vectors before that) were used rather than a continuous search: a search over
even a small architecture space against ~30 training rows would fit noise,
and there would be no honest way to report how many configurations were
tried. Three pre-declared configurations — one fewer than XGBoost's four,
given the added architectural complexity budget a GNN carries even at its
smallest setting — can be reported in full.

---

## 2. The graph representation and the candidate list

### 2.1 The graph each candidate trains on

Built once per component, independent of which candidate is being fit, from
`riskmesh.graph.Component` (the same object `riskmesh/graph.py`'s
`build_graph()` already produces) — not re-derived from `transactions.csv` or
any other path.

**Nodes.** One per account in the component, plus one per distinct
device/IP/instrument value used by `>= 2` of the component's accounts. This
is exactly the rule `__main__._write_graph_edges()` already applies to
produce `out/graph_edges.json` (group the component's transactions by
attribute value, keep a node only when `>= 2` accounts touch it), restricted
to `riskmesh.graph.LINKING_ATTRS` (`device_id`, `instrument_id`,
`ip_id`) rather than `__main__.GRAPH_LINKS`. **Merchants are excluded from
the graph, same as `riskmesh/graph.py`'s rule 1** — `LINKING_ATTRS` already
excludes them, which is why it is the reused set here rather than
`__main__.GRAPH_LINKS` (which additionally carries `merchant_id` for the UI's
burst story, not appropriate here).

**Edges.** Undirected, account-to-attribute-node, one per (account, node)
pair that survives the `>= 2` filter above — identical to
`_write_graph_edges()`'s edge list. No account-to-account edges are added
directly; two accounts that share a device are connected *through* the
device node, which is the actual GraphSAGE point: a 2-layer model can see
"my device's other accounts" without a hand-added account-account edge
duplicating what the device node already encodes.

**Node features — structural only, deliberately not the linear scorer's
signals.** Tier 2 already tested "same evidence (the linear scorer's 8
signals), different model (gradient boosting)". This phase's distinct
question is "does structure alone, learned by message passing, add anything
a flat feature vector cannot capture" — an XGBoost-shaped question would be
answered again, not a new one, if this phase reused `Candidate.signals`. So
each node gets exactly:

* a one-hot node-type indicator, 4 dimensions (`account`, `device`, `ip`,
  `instrument`);
* one degree feature: the node's degree *within this component's graph*,
  normalised the same way `score.py` normalises every signal — a **global**
  constant from `config.py`, never the component's own size (`score.py`'s own
  documented rule, "do not normalise a signal by its own component's size" —
  see `bugs.md` L1). For a device/IP/instrument node, degree is the count of
  distinct accounts touching that value, normalised by
  `cfg.max_device_degree` / `cfg.max_ip_degree` / `cfg.max_instrument_degree`
  respectively via `(k - 1) / (cap - 1)`, clipped to `[0, 1]` — the identical
  formula `score.py` uses for `device_sharing` / `ip_sharing` /
  `instrument_sharing`. For an account node, degree is the count of distinct
  attribute-nodes it connects to in this component, normalised by
  `max(cfg.max_device_degree, cfg.max_ip_degree, cfg.max_instrument_degree)`
  — config.py declares no per-account degree cap of its own, so the largest
  of the three existing attribute caps is reused rather than inventing a
  fourth config knob for one node-feature formula. This is a deliberate scope
  decision, not an oversight: **no signal values, no size, no exposure** enter
  a node feature anywhere.

Five features per node in total (4 one-hot + 1 degree). No candidate in §2.2
changes this — the representation is shared across all three, exactly as the
8-signal input space was shared across all four XGBoost candidates.

### 2.2 The candidate list

Fixed in advance. No candidate may be added after any result is seen.

| | policy | architecture | why it is on the list |
|---|---|---|---|
| **G1** | `G1_single_layer` | 1 aggregation layer, hidden dim 4, mean pooling, `weight_decay=1e-2`, 50 epochs, `lr=0.05` | smallest possible GraphSAGE — barely more than "average my neighbours," conservative for a ~30-row training set the same way `X1_shallow` was |
| **G2** | `G2_two_layer` | 2 aggregation layers, hidden dim 8, mean pooling, `weight_decay=1e-3`, 100 epochs, `lr=0.02` | a 2-hop receptive field — can see an account's device's OTHER accounts, a step up in capacity the same way `X2_moderate` was |
| **G3** | `G3_unregularised` | 2 aggregation layers, hidden dim 32, mean pooling, `weight_decay=0.0`, 300 epochs, `lr=0.05` | deliberately overfit-prone. **Expected to be refused by the gate** — included the same way `X4_unregularised` was for XGBoost, because a protocol whose gate never fires on a genuinely bad candidate has not been shown to work |

All three use: `torch.optim.Adam(model.parameters(), lr=..., weight_decay=...)`,
full-batch gradient descent (every train-split component's loss summed each
epoch — this benchmark's ~30-row train split has no need for mini-batching),
`torch.nn.functional.binary_cross_entropy_with_logits` as the loss, unweighted
(no `pos_weight` / class rebalancing — the XGBoost candidates used no
`scale_pos_weight` either, and introducing class weighting for the GNN alone
would not be the same comparison).

Aggregation, per layer: mean over a node's neighbours (GraphSAGE's mean
aggregator — with at most a handful of neighbours per node in these
components, "sample a fixed number of neighbours," the detail that gives
GraphSAGE its name for web-scale graphs, coincides with "use all of them"),
concatenated with the node's own features from the previous layer, one
linear layer, ReLU. After the declared number of layers, mean-pool the
resulting embeddings over **account nodes only** (device/IP/instrument nodes
contribute through message passing, not directly to the pooled vector) to
get one component-level embedding, then one final linear layer to a single
logit.

G3 is deliberately included as a candidate that should fail. **A protocol
whose gate never fires has not been shown to work.**

### 2.3 Seed and the determinism caveat

`torch.manual_seed(cfg.seed)` before every fit (selection fit and final
refit alike), plus `torch.use_deterministic_algorithms(True)` for the
duration of training. **Neural-network training has run-to-run variance
beyond what a fixed seed alone controls in general** — different hardware,
different BLAS backends, and multi-threaded reductions can all perturb
floating-point results even with a seed fixed. This protocol controls for it
as far as `torch.manual_seed()` and CPU-only, single-process execution
allow, the same way `config.py`'s own docstring scopes its determinism claim
to "one interpreter version" rather than claiming something stronger than
what was actually tested. §8 records whether the installed `torch` version,
on this machine, in fact reproduces bit-identical refits — a finding, not an
assumption.

---

## 3. The gate — reused unchanged from the weight search and the XGBoost search

A candidate that fails **any of three** gates **is not a candidate**. It does
not receive an expected-loss figure that is later discarded; there is no
figure.

| gate | bound | enforced by |
|---|---|---|
| non-triviality panel | verdict `PASS` | `PanelGateFailure` |
| hard negatives inside the positive range | `>= 4` | `DifficultyGateFailure` |
| positives below the top negative | `>= 0.45` | `DifficultyGateFailure` |

These are `costmodel.MIN_HARD_NEGATIVES_IN_RANGE` and
`costmodel.MIN_POSITIVES_BELOW_MAX_NEGATIVE`, imported into `riskmesh/gnn.py`
and used through `costmodel.gated_expected_loss()` and
`costmodel.panel_verdict()` directly — **not redeclared**. The whole point of
this phase is that GraphSAGE's candidates are held to the identical bar the
weight vectors and XGBoost's candidates were; a new bound tuned for a third
model family would defeat the purpose of having a gate at all.

**Why this matters at least as much here as for XGBoost.** A 2-layer,
hidden-dim-32 message-passing network has comparable or greater capacity
than a 300-tree unregularised gradient boosted ensemble to find a way to make
the *benchmark* look easier rather than to genuinely discriminate rings from
families, and — per `task_today.md`'s framing — a GNN typically needs *more*
data to train stably than a tree ensemble does, not less, on a ~30-row train
split. The gate is therefore enforced structurally, exactly as before:
`gated_expected_loss()` raises `PanelGateFailure` or `DifficultyGateFailure`
instead of returning a number, and the search records the refusal and moves
on.

**Two further structural guarantees, mirroring `select_weights()` /
`select_xgboost_model()`:**

* `select_gnn_model()` takes design candidates as its whole input and asserts
  it received nothing else.
* `evaluate_frozen_gnn_policy()` raises `GNNPolicyNotFrozen` unless the
  winning configuration is already written to disk, **and also when the
  frozen record exists but names no winner** — the same `winner is None`
  refusal `riskmesh.ml.MLPolicyNotFrozen` already enforces, copied rather than
  reinvented.

---

## 4. Fitting discipline — train vs. validation vs. design vs. test

Identical shape to `xgboost_protocol.md` §4, restated for this model family:

1. **Model selection (fitting).** Each of the three candidates is fit on
   **TRAIN split components only** — not train+validation. Full-batch
   gradient descent for the candidate's declared fixed epoch count, freshly
   initialised (`torch.manual_seed(cfg.seed)`) each time.
2. **Gate evaluation.** The train-fit model scores **validation** components
   only — out-of-sample, the rows it was not fit on, with the model in
   `eval()` mode and gradients disabled. `panel_verdict()` and the two
   difficulty bounds are computed on this validation-only view, never mixed
   with train's in-sample predictions, for the identical reason
   `xgboost_protocol.md` §4.2 gives: in-sample predictions on rows the model
   was trained on are biased toward separation regardless of whether the
   model generalises.
3. **Threshold / objective.** Expected loss is minimised by sweeping
   thresholds 0.00–1.00 in 0.01 steps, scored on that same **validation-only**
   out-of-sample view, via `costmodel.expected_loss()` through
   `costmodel.gated_expected_loss()`, reusing `costmodel.derive_costs()`'s
   already-derived costs (computed on train+validation, unchanged) without
   re-deriving them.
4. **Refit for the final read.** Once a candidate is selected, its SAME
   hyperparameter configuration is refit from a fresh initialisation
   (`torch.manual_seed(cfg.seed)` again) on **train+validation combined**
   (all design data) for the same declared epoch count, before it is used to
   score the held-out test split. The model used to produce the selection
   numbers in §8's candidate table (train-fit) is therefore **not** the same
   model object used for the §8 held-out read (train+validation-fit) — both
   are the same architecture and hyperparameters, fit on different, always
   design-only, data, from the same fixed seed.

---

## 5. Procedure

1. Regenerate `out/` (`rm -rf out && python -m riskmesh`) and confirm the
   Tier 1 baseline is still current, reading it from `out/eval_report.json`
   rather than trusting a quoted number.
2. Build the standard candidate set once (generator untouched, current
   weights) and the per-component graph representation (§2.1) once, from
   `graph.components` — independent of which GraphSAGE candidate is being
   fit.
3. Derive costs from **train+validation** (`costmodel.derive_costs`), reused
   unchanged (not re-derived for this phase).
4. For each of the three candidates, in the declared order:
   a. Fit the architecture on **train** components' graphs for the declared
      fixed epoch count, Adam, the declared `lr` / `weight_decay`.
   b. Score **validation** components only with that fit (out-of-sample,
      `model.eval()`, no grad), replacing `.score` via
      `dataclasses.replace(c, score=pred)`.
   c. Run the non-triviality panel and the two difficulty gates on that
      validation-only view (§3, §4).
   d. If any gate fails: record which exception fired and the failing
      checks. **No expected loss.** Next candidate.
   e. Otherwise sweep thresholds 0.00–1.00 in 0.01 steps on that same
      validation-only view and take the minimum expected loss.
5. Select the candidate with the lowest validation expected loss among
   feasible candidates. Ties break toward the earlier-declared (and by
   construction more conservative) candidate — G1 before G2 before G3 —
   never toward the more complex configuration. If no candidate is feasible,
   that is the finding: no fourth candidate is added and no gate is
   loosened.
6. Refit the winning hyperparameter configuration on **train+validation
   combined** (§4.4).
7. Write the winner, its threshold, its validation expected loss, its panel
   row, the full three-candidate table, and the installed `torch.__version__`
   to `experiments/graphsage_policy.json`. **Freeze.** Copy byte-identically
   to `out/graphsage_policy.json`, mirroring `xgboost_policy.json`'s pattern
   in `__main__.py`.
8. Read the held-out split **once**, through `evaluate_frozen_gnn_policy()`
   (using the train+validation refit from step 6), and report precision,
   recall, F1, FPR, ring recovery, expected loss, review rate — the same set
   `xgboost_protocol.md` §5 step 8 reports.
9. No second read. If the held-out result disappoints, that is the result.

---

## 6. What "beat the Tier 1 baseline" means

Stated up front, before any candidate's held-out number is known: **beating
Tier 1 means the selected candidate's held-out F1 or held-out expected loss
is at least as good as Tier 1's frozen numbers, read fresh from
`out/eval_report.json` at the time this protocol is run** (F1 higher is
better; expected loss lower is better) — not a number copied from an earlier
phase's document, since a re-run of `python -m riskmesh` is part of this
protocol's own step 1 and the frozen numbers are re-confirmed there. Both are
reported regardless of which, if either, wins.

**If no candidate is feasible, or the best feasible candidate does not beat
Tier 1, that is the finding, reported as such.** It is not a reason to add a
fourth candidate, loosen a gate, extend training, or re-derive costs until
the answer looks better. This project has already reported an XGBoost
attempt where none of four candidates reached a held-out reading at all
(`xgboost_protocol.md` §8) and a 19x validation-to-test gap
(`weight_search_protocol.md` §8) without adjusting anything after the fact to
make either look better. Per `task_today.md`: **the realistic, scientifically
honest expectation for this phase is another "no feasible candidate" result**,
and that is reported exactly as plainly as the XGBoost outcome was if it
occurs.

---

## 7. What would invalidate this protocol

Stated so it is falsifiable:

* Any candidate added, removed, or redefined after a result is seen.
* Any node feature added beyond the one-hot type indicator and the single
  degree feature, after a result is seen (in particular: any of the linear
  scorer's 8 signal values, size, or exposure).
* Any epoch count, learning rate, or weight decay changed after a result is
  seen, for any candidate.
* Any cost input changed after seeing which configuration wins.
* Any expected-loss number produced for a gate-failing candidate.
* More than one held-out read.
* The gate's bounds changed after step 4 (§5) begins — including changing
  them "for GraphSAGE specifically" rather than for the whole codebase.
* The selection fit (train-only) and the final-read fit (train+validation)
  being conflated — i.e., a candidate's §8 table row using a model that ever
  saw validation features during the fit that produced that row's numbers.
* `torch_geometric` or `dgl` used anywhere in this phase, under any
  circumstance — the hand-rolled aggregation is the specified approach, not a
  fallback to reach for if the hand-rolled version is inconvenient.

If any of these happens, the protocol is void and the selection is re-run
from a new frozen record.

---

## 8. Outcome — one candidate feasible, held-out read taken, does not beat Tier 1

Record: `experiments/graphsage_policy.json` (byte-copied to
`out/graphsage_policy.json`). Installed `torch.__version__` **2.13.0+cpu**.
Costs re-derived on the current benchmark (identical derivation to
`weight_search_protocol.md` §4/§8 and `xgboost_protocol.md` §8, same
`derive_costs()` call, same design split): `C_review` 500.00, `C_fn`
68,399.84, `C_fp` 398.43, ratio 171.7:1. Config fingerprint
`c3ee14627c2c2ce2`, seed 20260824.

**Unlike Tier 2's XGBoost attempt, one candidate did clear all three gates.**
This is a different outcome from `task_today.md`'s stated expectation, and it
is reported exactly as it occurred, not adjusted toward the expectation.

| policy | panel | pbmn | hard-neg | distinct predictions | feasible | reason |
|---|---|---|---|---|---|---|
| **G1_single_layer** | PASS | 0.7500 | 8 | 15 | **yes** | clears all three gates |
| **G2_two_layer** | FAIL | 0.0000 | 0 | 21 | no | genuine over-separation |
| **G3_unregularised** | FAIL | 0.0000 | 0 | 12 | no | genuine over-separation, as predicted in §2.2 |

**G1, the smallest architecture, is the only feasible candidate.** Its
1-layer, hidden-dim-4, heavily-`weight_decay`'d configuration produces 15
distinct validation predictions (not a degenerate constant), passes the
non-triviality panel with margin (`positives_below_max_negative` 0.75,
comfortably above the 0.45 bound; 8 hard negatives inside the positive range,
double the minimum of 4), and reaches a validation expected loss of
**12,085.87** at threshold 0.18 (tp 8, fp 9, fn 0, tn 14).

**G2 and G3 both fail the same way, and it is the over-separation mechanism,
not the degenerate-constant one XGBoost's X1–X3 showed.**
`n_unique_validation_predictions` is 21 and 12 respectively — both models
produce plenty of distinct scores — yet `positives_below_max_negative` reads
**exactly 0.0000** for both: the single top-scoring negative component
outscores every positive on validation. This is consistent with
`graphsage_protocol.md`'s own §3 prediction that a 2-layer, higher-capacity
network "has comparable or greater capacity than a 300-tree unregularised
gradient-boosted ensemble to find a way to make the benchmark look easier" —
here, on this ~30-row train split, the additional aggregation layer and
higher hidden dimension push the model to a validation ranking that inverts
rather than merely flattens the classes. G3 was included specifically
because it was expected to be refused (§2.2); it was. **G2's refusal is the
less expected finding**: a 2-hop receptive field with a genuinely small
`weight_decay=1e-3` (not zero) was intended as a middle ground, comparable in
spirit to `X2_moderate`, and it failed exactly as badly as the deliberately
overfit G3. This suggests the second aggregation layer itself, not only the
absence of regularisation, is what this benchmark's ~30-row train split
cannot support — a finding this protocol did not anticipate going in, and
one a future GNN attempt on this dataset should treat as informative rather
than re-litigate with a fourth similarly-sized 2-layer candidate under this
same frozen record.

**Winner: G1_single_layer**, threshold 0.18, validation expected loss
12,085.87. Per §5 step 5, ties would break toward the earlier-declared
candidate, but no tie arose — G1 is the only feasible candidate.

### Step 8 — the held-out read

`evaluate_frozen_gnn_policy()` was called against the frozen record above.
Because a winner exists, it refit `G1_single_layer`'s architecture from a
fresh initialisation (`torch.manual_seed(cfg.seed)`) on **train+validation
combined** and scored the test split once:

| metric | value |
|---|---|
| precision | 0.3500 |
| recall | 0.8750 |
| F1 | **0.5000** |
| false positive rate | 0.5652 |
| ring recovery | 7/8 (87.5%) |
| expected loss | **83,579.43** |
| review rate | 0.6452 (tp 7, fp 13, tn 10, fn 1) |

**No second read was taken.** This is the only held-out number this record
permits.

### Verdict against the Tier 1 baseline

Tier 1's frozen numbers, read fresh from `out/eval_report.json` and
`out/weight_policy.json` after `rm -rf out && python -m riskmesh` (step 1 of
§5, run immediately before this candidate set was built): **F1 0.7778,
held-out expected loss 74,595.13, threshold 0.18**, on 31 test components —
unchanged from every prior phase's frozen number, confirmed rather than
assumed.

**GraphSAGE does not beat Tier 1.** G1_single_layer's held-out F1 (0.5000) is
below Tier 1's 0.7778, and its held-out expected loss (83,579.43) is *higher*
(worse) than Tier 1's 74,595.13. Both comparisons point the same direction:
the GNN generalises substantially worse than the linear scorer on this
benchmark's test split, despite clearing every gate on validation with
margin.

**This is the same shape of finding `weight_search_protocol.md` §8 already
reported once (a large validation-to-test gap) rather than the shape
`xgboost_protocol.md` §8 reported (no candidate ever reaches a held-out
reading).** G1 passed the gate comfortably on validation — `pbmn` 0.75
against a 0.45 bound, not a hair above it — and still lost badly on test:
tp fell from 8 (validation) to 7, but fp rose from 9 to 13 out of only 23
test negatives, nearly triple Tier 1's 3 false positives on the identical
test split. The gate's job is to refuse a candidate whose *validation*
behaviour cannot be trusted to report an honest expected loss; it is not, and
was never claimed to be, a guarantee that a candidate clearing it will
generalise to test. That gap is exactly what a single held-out read, taken
once and reported regardless of outcome, exists to surface.

**No further read is permitted under this record.** Any future GraphSAGE
comparison — a different node-feature set, a different candidate list, more
training data — needs its own frozen protocol.
