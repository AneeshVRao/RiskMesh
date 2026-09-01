# Weight-search protocol — frozen before any candidate is scored

**Status: WRITTEN, NOT YET RUN (re-freeze pending — Tasks 3–5 benchmark).**
Tasks 3–5 rebuilt the benchmark itself (five ring types instead of one, four
hard-negative cluster types instead of one, population raised to 19,310
transactions) and moved the config fingerprint from `c3ee14627c2c2ce2` to
`28e054e8fa8436e9`. Every number this protocol had frozen under the old
fingerprint (Phase 12's re-run, previously recorded in §8 — `A_baseline` won
in one pass, held-out F1 0.7778, expected loss 74,595.13) describes a run that
no longer reproduces, so §8 has been cleared back to a pending placeholder and
this document is committed in that state, **before** `select_weights()` is run
against the new benchmark — exactly the discipline this protocol has followed
at every prior re-freeze (Phase 10's first run, Phase 11's fold-back, Phase
12's RNG-isolation re-run; the superseded §8 tables for each are in git
history, not reproduced here). §8 is appended only after
`experiments/weight_policy.json` exists and the single held-out read has been
taken through `evaluate_frozen_policy()`.

**The five candidates (§2), the three gates (§3), the objective (§4), and the
fold-back procedure (§5) are unchanged from every prior run.** This re-freeze
does not add, remove, or redefine a candidate to chase a result (G5). Only the
generator producing the rows they are scored against has changed. Section 4's
specific cost figures (median exposures, the 171.7:1 ratio) are the *prior*
run's numbers, kept as a worked illustration of the derivation method; they
will be recomputed fresh against the new benchmark in §8, not assumed to
still hold.

This is the last thing frozen before Tier 1's weight and cost work. It follows
the same discipline as every experiment in this build: the rules are written
down while the answer is still unknown, so they cannot be adjusted once the
numbers are visible.

Code: `riskmesh/costmodel.py`. Evidence for why the gate exists: `bugs.md` L2.

---

## 1. What is being selected, and what is not

**Selected:** one weight vector, from a fixed list of five candidates, by minimum
expected loss on validation.

**Not selected here:** the generator (frozen since E2), any signal definition,
the ground-truth rule, or the split. The manual-review/abstention band is a
separate later step — this protocol chooses weights, and treats every flagged
component as reviewed.

**No search space.** Five named candidates, not a grid or an optimiser. A
continuous search over eight weights on 16 design positives would fit noise, and
there would be no honest way to report how many configurations were tried. Five
pre-declared policies can be reported in full.

---

## 2. The candidate list

Fixed in advance. No candidate may be added after any result is seen.

| | policy | definition | why it is on the list |
|---|---|---|---|
| **A** | `A_baseline` | current hand-set Tier 0 weights | control — everything is measured against this |
| **B** | `B_equal` | equal weight on every signal not already zeroed by a filed RISK item | tests whether the hand-tuned ratios bought anything |
| **C** | `C_separation_proportional` | weight ∝ ring-minus-family delta, non-positive deltas zeroed | the diagnostic that drove every RISK fix, used directly as a policy |
| **D** | `D_drop_flagged` | zero `instrument_sharing` and `merchant_concentration` | the RISK-004 + RISK-002 direction. **Expected to be refused by the gate** |
| **E** | `E_drop_temporal` | zero `temporal_burst` | tests D1 — the ablation found this signal redundant |

D is deliberately included as a candidate that should fail. **A protocol whose
gate never fires has not been shown to work.**

---

## 3. The gate — structural, not conventional

A weight vector that fails **any of three** gates **is not a candidate**. It does
not receive an expected-loss figure that is later discarded; there is no figure.

| gate | bound | enforced by |
|---|---|---|
| non-triviality panel | verdict `PASS` | `PanelGateFailure` |
| hard negatives inside the positive range | `>= 4` | `DifficultyGateFailure` |
| positives below the top negative | `>= 0.45` | `DifficultyGateFailure` |

**Panel PASS is necessary and no longer sufficient.** The panel's own bounds
(`>= 0.20` and `>= 1`) are the minimum for a dataset to be worth evaluating on at
all; the gate demonstration showed policy B clearing them while spending most of
the benchmark's difficulty. The two additional bounds are **absolute, not a
margin from the incumbent** — a margin from A would move whenever A moved, so a
sequence of individually reasonable changes could ratchet difficulty down one
accepted step at a time.

**These were declared before candidate selection, not fitted after it.** The
reason is `bugs.md` L2 and it is a measured one: held-out F1 rose 0.8000 → 0.8889
twice, by two unrelated mechanisms, and the panel went PASS → FAIL both times. A
higher score on this benchmark can mean a better scorer or an easier benchmark,
and the metric cannot tell them apart. Difficulty is therefore constrained before
expected loss is allowed to matter, rather than reported alongside it afterwards.
`DifficultyGateFailure` subclasses `PanelGateFailure`, so anything catching the
gate catches both.

This is enforced the way `held_out_view()` enforces the test-set freeze — by what
the function is able to do:

```python
def gated_expected_loss(cfg, design, threshold, costs, score_on=None):
    v = panel_verdict(cfg, design)
    if v["verdict"] != "PASS":
        raise PanelGateFailure(...)          # no number is returned, ever
    if v["hard_negatives_inside_positive_range"] < MIN_HARD_NEGATIVES_IN_RANGE:
        raise DifficultyGateFailure(...)
    if v["positives_below_max_negative"] < MIN_POSITIVES_BELOW_MAX_NEGATIVE:
        raise DifficultyGateFailure(...)
    return expected_loss(design if score_on is None else score_on,
                         threshold, costs)
```

Gates are evaluated on train+validation, so difficulty is measured against all 16
design positives. `score_on` carries the validation rows, because a threshold
must be chosen on validation alone. Both arguments are design views; neither can
carry a test row.

`expected_loss()` exists separately and is not called anywhere in the selection
path except through `gated_expected_loss()`. The search records the refusal and
the failing checks for the report, then moves on.

**Why this rather than "score it and discard it if it fails".** `bugs.md` L2:
held-out F1 improved from 0.8000 to 0.8889 twice, by two unrelated mechanisms,
and the panel went PASS → FAIL both times. A benchmark whose difficulty is partly
produced by the model's own components will hand an optimiser cheap wins that
consist of making the task easier. If a failing candidate can still produce a
number, that number will eventually be compared against, argued about, or quoted.

**Two further structural guarantees:**

* `select_weights()` takes design candidates as its whole input and asserts it
  received nothing else — identical in shape to `select_threshold()`. The
  threshold sweep inside it uses validation rows only.
* `evaluate_frozen_policy()` raises `PolicyNotFrozen` unless the winning policy is
  already written to disk.

---

## 4. Expected loss

```
expected_loss = FN × C_fn  +  FP × C_fp  +  (TP + FP) × C_review
```

Every flagged component costs a review whether or not it was right; a missed ring
costs its exposure; a wrongly-escalated legitimate component costs a review plus
business friction.

### Cost inputs, derived from the dataset (PRD §"Cost Inputs")

Computed on **train+validation only**, by `derive_costs()`. Medians, not means —
component exposure is long-tailed, and a mean would let one large ring set the
price of every decision.

| input | value (INR) | derivation |
|---|---|---|
| `C_review` | **500.00** | 20 analyst-minutes per component at INR 1500/hour fully loaded |
| `C_fn` | **68,399.84** | median ring-component exposure (INR 68,399.84) × `FN_ABSORBED_FRACTION` 1.00 |
| `C_fp` | **398.43** | `FP_FRICTION_RATE` 0.02 × median negative-component exposure (19,921.59) — friction only, no embedded review term (Phase 10 fixed `deferred_decisions.md` D3: the generic `(TP+FP) × C_review` term already prices one review per flagged component) |

Data behind these (Phase 12 benchmark, after the ring-injector RNG-isolation
fix): 16 positive and 53 negative design components; median ring exposure
68,399.84; median negative exposure 19,921.59. No round numbers are presented
without a derivation.

**The three assumptions, named as assumptions:**

1. `ANALYST_MINUTES_PER_COMPONENT = 20` at `ANALYST_COST_PER_HOUR = 1500`. The
   dataset carries no analyst-effort figure; this is the one input it cannot
   supply.
2. `FN_ABSORBED_FRACTION = 1.00` — an undetected ring's transactions settle and
   the chargebacks land on the platform. The pessimistic end.
3. `FP_FRICTION_RATE = 0.02` — a wrongly-blocked legitimate customer costs the
   margin on disrupted volume plus churn risk, not their whole exposure.

**Required sensitivity table.** The selected policy must be re-reported at
`FN_ABSORBED_FRACTION` ∈ {0.50, 0.75, 1.00} and `FP_FRICTION_RATE` ∈ {0.01, 0.02,
0.05}. If the winner changes across that grid, the report says so plainly rather
than quoting the base case alone.

### A known property of these costs, flagged before running

`C_fn / C_fp` is **171.7:1** (Phase 10/11 reported 249.7:1 against the
pre-RNG-fix benchmark; the fix changed the underlying exposure distribution,
not `FP_FRICTION_RATE` or the derivation itself — the original run's 88:1, from
before D3 dropped the embedded review term from `C_fp`, remains the oldest
reference point). At that ratio the loss-minimising threshold will be very low
and may collapse to
*flag everything*, which is a real property of fraud
economics rather than a bug. The search must therefore report, for the selected
policy, the **review rate** and the loss of the trivial flag-everything policy. If
the winner is not meaningfully better than flag-everything, that is the finding
and it gets reported as such — it is an argument for the abstention band, not a
reason to adjust the costs until the answer looks better.

---

## 5. Procedure

1. Derive costs from **train+validation** (`derive_costs`). Freeze them.
2. For each of the five candidates, in the declared order:
   a. Rescore all components under that weight vector (generator untouched).
   b. Run the non-triviality panel on **train+validation**.
   c. If the verdict is not PASS: record `PanelGateFailure` and the failing
      checks. **No expected loss.** Next candidate.
   d. Otherwise sweep thresholds 0.00–1.00 in 0.01 steps on **validation only**
      and take the minimum expected loss.
3. Select the candidate with the lowest validation expected loss. Ties break
   toward the policy with the higher `positives_below_max_negative`, then toward
   A (the incumbent) — never toward the more complex change.
4. **The fold-back rule.** If the winning candidate from step 3 is not
   `A_baseline`, its weight vector is folded into `Config()._default_weights()`
   as the new incumbent, and the entire search (steps 1-3) is re-run from
   generation against it. This converges when the new incumbent, now labelled
   `A_baseline`, wins outright — checked explicitly by re-running step 3
   against it, not assumed because the vectors look identical. Capped at 2
   iterations: if the second pass's winner is still not `A_baseline`, that is
   non-convergence, and it is reported as a blocking finding rather than
   forced through with a third iteration. (Written here, in this document's
   own procedure, rather than left as a citation into a phase's scratch file —
   `task_today.md` and equivalents are gitignored and deleted at every phase
   close, so a rule that lives only there is unverifiable to a later reader.
   Phase 11 needed one extra iteration to reach this fixed point; Phase 12
   did not need to invoke this rule at all, since `A_baseline` won outright on
   the first pass — see §8.)
5. Write the winner, its threshold, its validation loss, its panel row and the
   full five-candidate table to `out/weight_policy.json`. **Freeze.**
6. Read the held-out split **once**, through `evaluate_frozen_policy()`, and
   report precision, recall, F1, FPR, ring recovery, expected loss, review rate
   — and `positives_below_max_negative` alongside them, per L2.
7. No second read. If the held-out result disappoints, that is the result.

---

## 6. Gate demonstration (already run — validation+train only, no selection)

Run before asking for confirmation, precisely so the gate is shown to be real
rather than asserted. Expected loss below is at a **fixed 0.25 threshold**, not a
selected one. **Historical record, pre-Phase-10** — computed against the
Tier 0 seven-signal benchmark before the hybrid pool-funded ring type and the
8th signal existed. Kept unchanged because it demonstrates the gate mechanism
itself, not this run's outcome; §8 below carries the current numbers.

```
A_baseline                   panel PASS  pbmn 0.5625  hard-neg 4
                             -> expected loss 13,392.92
B_equal                      panel PASS  pbmn 0.3125  hard-neg 1
                             -> expected loss 13,392.92
C_separation_proportional    panel FAIL  pbmn 0.0000  hard-neg 0
                             -> REFUSED -- PanelGateFailure, no number produced
D_drop_flagged               panel FAIL  pbmn 0.1250  hard-neg 1
                             -> REFUSED -- PanelGateFailure, no number produced
E_drop_temporal              panel PASS  pbmn 0.5625  hard-neg 4
                             -> expected loss 14,741.15
```

**The gate fires on two of five, and only one of them was predicted.**

D was expected to fail. **C was not.** Weighting proportional to ring-minus-family
separation puts **0.658 on `account_newness`** — the signal whose single-signal F1
is already 0.9412 — and takes `positives_below_max_negative` to **0.0000** with
**zero** hard negatives left in the positive range. The benchmark is destroyed
completely. C is the most principled-looking policy on the list, derived from the
exact diagnostic this build has used to fix three RISK items, and it is the worst
one. That is L2's mechanism appearing unprompted, in the policy least likely to
be suspected.

**One thing this exposes about the gate itself, flagged rather than fixed
unilaterally.** Policy B *passes* the panel while taking
`positives_below_max_negative` from 0.5625 to 0.3125 and hard negatives in the
positive range from 4 to 1. The panel's bound is `>= 0.20`, so B clears it while
having eaten most of the benchmark's difficulty. The gate is real but its
threshold may be too permissive to protect what L2 says needs protecting.

**Resolved, and this is where the two difficulty gates came from.** The decision
was taken here — before `select_weights()` existed and before any candidate had
an expected-loss figure — to add two *absolute* bounds rather than a margin from
A: `hard_negatives_inside_positive_range >= 4` and
`positives_below_max_negative >= 0.45`. A relative margin was rejected because it
moves whenever the incumbent moves. B is refused under the tightened gate; see
§3 and the outcome in §8.

---

## 7. What would invalidate this protocol

Stated so it is falsifiable:

* Any candidate added, removed or redefined after a result is seen.
* Any cost input changed after seeing which policy wins, other than through the
  declared sensitivity table.
* Any expected-loss number produced for a panel-failing candidate.
* More than one held-out read.
* The gate's bound changed after step 2 begins.

If any of these happens, the protocol is void and the selection is re-run from a
new frozen record.


---

## 8. Outcome — PENDING

Not yet run. This section is populated, in full, only after
`python -m riskmesh.freeze weights` has produced
`experiments/weight_policy.json` against the Tasks 3–5 benchmark
(fingerprint `28e054e8fa8436e9`) and the single held-out read has been taken
through `evaluate_frozen_policy()`. The prior run's tables (Phase 10, Phase
11's fold-back, Phase 12's RNG-isolation re-run — most recently `A_baseline`
winning outright at threshold 0.18, held-out F1 0.7778) are superseded and
live in git history at this section's prior revisions, not reproduced here,
per this project's own rule that a stale number is not kept standing next to
a status header that contradicts it.

**No further read is permitted under any *prior* record.** This re-run gets
its own single held-out read, taken once, after this file is committed and
the freeze stage runs.
