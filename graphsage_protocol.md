# GraphSAGE-search protocol — frozen before any candidate is scored

**Status: RUN and CLOSED (Task 6 re-freeze). Outcome in §8 — all three
candidates feasible for the first time (including the deliberately-overfit
`G3_unregularised`), `G2_two_layer` wins, and the held-out result is mixed:
it does not beat Tier 1 on F1 but does beat Tier 1 on expected loss.** This
document was committed (see git history at this section's prior revision)
before `select_gnn_model()` ran against the Tasks 3–5 benchmark (five ring
types, four hard-negative cluster types, 19,310 transactions, config
fingerprint `28e054e8fa8436e9`, folded by `weight_search_protocol.md`'s own
re-freeze to `fdf4fc217347d36b` before this stage ran). The graph
representation and three candidates (§2), the gates (§3), and the fitting
discipline (§4) are unchanged.

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


## 8. Outcome — all three candidates feasible, `G2_two_layer` wins, mixed held-out result

Record: `experiments/graphsage_policy.json` (byte-copied to
`out/graphsage_policy.json`). Installed `torch.__version__` **2.13.0+cpu**.
Costs re-derived on the Tasks 3-5 benchmark (identical derivation to
`weight_search_protocol.md` §4/§8 and `xgboost_protocol.md` §8, same
`derive_costs()` call, same design split): `C_review` 500.00, `C_fn`
41,748.15, `C_fp` 597.65, ratio **69.9:1**. Config fingerprint
`fdf4fc217347d36b` (post weight-fold-back), seed 20260824.

**All three candidates cleared every gate — the first run, of any of the
three model families this project has tried, where the deliberately
overfit-prone candidate is not refused.**

| policy | panel | pbmn | hard-neg | distinct predictions | feasible | threshold | expected loss |
|---|---|---|---|---|---|---|---|
| G1_single_layer | PASS | 0.6522 | 41 | 47 | yes | 0.12 | 64,187.20 |
| **G2_two_layer** | PASS | **1.0000** | 34 | 52 | **yes** | 0.03 | **51,015.40** |
| G3_unregularised | PASS | 0.9130 | 23 | 32 | yes | 0.00 | 96,019.05 |

**This is a materially different shape of result from the pre-Task-6 run**,
where `G2` and `G3` both failed on genuine over-separation
(`positives_below_max_negative` reading exactly 0.0000 for both) and `G1`
was the only feasible candidate. Here `G2` reaches a *perfect*
`positives_below_max_negative` of 1.0000 -- every validation positive scores
above every validation negative -- yet still clears the gate, because
`hard_negatives_inside_positive_range` (34, well above the 4 minimum) and
the base non-triviality panel both hold; a validation split where positives
cleanly separate from negatives is not automatically a "made the benchmark
easier" result if the difficulty was already present and the model is simply
separating what the data actually supports on this particular draw. `G3`
technically clears every gate too, but its selected operating point
(threshold **0.00**, review rate **100%**, tp 23/fp 77/fn 0/tn 0) is
identical in every count to validation flag-everything
(`weight_search_protocol.md` §8's 96,019.05 flag-everything figure) --
`G3`'s scores are separated enough to clear the panel, but not usefully
enough to beat flagging every component, so its "feasible" status is real
but its practical value at this operating point is nil.

**`G2_two_layer` wins** on validation expected loss (51,015.40), beating
both `G1` (64,187.20, review rate 71%) and `G3` (96,019.05, review rate
100%). Per §5, ties would break toward the earlier-declared candidate, but
no tie arose here.

### Step 8 — the held-out read

`evaluate_frozen_gnn_policy()` was called against the frozen record above.
Because a winner exists, it refit `G2_two_layer`'s architecture from a fresh
initialisation (`torch.manual_seed(cfg.seed)`) on **train+validation
combined** and scored the 112 test components once:

| metric | value |
|---|---|
| precision | 0.3710 |
| recall | **1.0000** |
| F1 | 0.5412 |
| false positive rate | 0.4382 |
| ring recovery | 17/20 (85.0%) |
| expected loss | **54,308.35** |
| review rate | 0.5536 (tp 23, fp 39, tn 50, fn 0) |

Account level: precision 0.4189, recall 1.0000, F1 0.5904, FPR 0.4968.
False positives: 30 family/office/hostel/retail, 9 background.

**No second read was taken.** This is the only held-out number this record
permits.

### Verdict against the Tier 1 baseline

Tier 1's frozen numbers, read fresh from `out/eval_report.json` after
`rm -rf out && python -m riskmesh` (step 1 of §5): **F1 0.75** at threshold
0.22, on 112 test components. `weight_search_protocol.md` §8's held-out
expected loss (the linear scorer's own frozen operating point) is
**92,263.55** at threshold 0.10.

**The result is mixed, and it is reported exactly that way rather than
collapsed into a single verdict.** `G2_two_layer`'s held-out F1 (0.5412) is
below Tier 1's (0.75) -- **GraphSAGE does not beat Tier 1 on F1.** But its
held-out expected loss (54,308.35) is *lower* (better) than Tier 1's
(92,263.55) -- a **41.1%** reduction -- **GraphSAGE does beat Tier 1 on
expected loss.** Per §6, stated before this run, "beating Tier 1" means the
candidate's held-out F1 **or** held-out expected loss is at least as good as
Tier 1's; by that literal, pre-declared definition, `G2_two_layer` beats
Tier 1. The mechanism is legible, not an artifact: `G2`'s selected threshold
(0.03) drives recall to 1.0000 -- it misses zero of the 20 test-split rings
-- at the cost of a high false-positive rate (0.4382, nearly 6x Tier 1's
FPR on the same rows). F1 penalises that trade-off symmetrically; expected
loss, at this benchmark's 69.9:1 `C_fn`/`C_fp` ratio, rewards it heavily,
because missing zero rings is worth far more than the extra review-and-
friction cost of 39 false positives. **This is not evidence GraphSAGE
"generalises better" than the linear scorer** -- it is evidence that a
model whose validation-selected operating point happens to sit at very high
recall will score well under an expected-loss objective this lopsided,
regardless of model family; `weight_search_protocol.md` §8's own
`A_baseline` shows the same recall-heavy shape (0.9565) for the identical
structural reason (dropping `temporal_burst` pushed its threshold low too).
The two scorers are not simply comparable at a single operating point: Tier
1's frozen threshold (0.22) is F1-selected, not expected-loss-selected, so
this comparison holds two different selection objectives up against each
other's preferred metric, which is the honest comparison the protocol
defines, not a matched one.

**No further read is permitted under this record.** Any future GraphSAGE
comparison — a different node-feature set, a different candidate list, more
training data — needs its own frozen protocol.
