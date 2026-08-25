# Weight-search protocol — frozen before any candidate is scored

**Status: RUN. Outcome in §8 — A_baseline retained.** The three gates were all
defined before `select_weights()` was implemented, and the two difficulty gates
were added before any candidate had been scored on expected loss. The held-out
split has **not** been read; step 5 is still pending review.

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
continuous search over seven weights on 16 design positives would fit noise, and
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

* `select_weights()` takes validation candidates as its whole input and asserts it
  received nothing else — identical in shape to `select_threshold()`.
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
| `C_fn` | **74,645.29** | median ring-component exposure (INR 74,645.29) × `FN_ABSORBED_FRACTION` 1.00 |
| `C_fp` | **848.23** | one review (500.00) + `FP_FRICTION_RATE` 0.02 × median negative-component exposure (17,411.63) |

Data behind these: 16 positive and 53 negative design components; median ring
exposure 74,645.29; median negative exposure 17,411.63. No round numbers are
presented without a derivation.

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

`C_fn / C_fp` is **88:1**. At that ratio the loss-minimising threshold will be
very low and may collapse to *flag everything*, which is a real property of fraud
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
4. Write the winner, its threshold, its validation loss, its panel row and the
   full five-candidate table to `out/weight_policy.json`. **Freeze.**
5. Read the held-out split **once**, through `evaluate_frozen_policy()`, and
   report precision, recall, F1, FPR, ring recovery, expected loss, review rate
   — and `positives_below_max_negative` alongside them, per L2.
6. No second read. If the held-out result disappoints, that is the result.

---

## 6. Gate demonstration (already run — validation+train only, no selection)

Run before asking for confirmation, precisely so the gate is shown to be real
rather than asserted. Expected loss below is at a **fixed 0.25 threshold**, not a
selected one.

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

**Proposed, needs your decision before step 2 runs:** add a no-regression rule to
the gate — a candidate must not reduce `positives_below_max_negative` below A's
0.5625 by more than a stated margin, or must not drop
`hard_negatives_inside_positive_range` below 4. This would refuse B as well. I
have not applied it, because tightening a gate after seeing which candidates it
catches is exactly the move this protocol exists to prevent; it needs to be your
call, made now, before any selection runs.

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

## 8. Outcome — run on validation only, held-out untouched

Record: `out/weight_policy.json`.

| policy | panel | pbmn | hard-neg | feasible | threshold | expected loss |
|---|---|---|---|---|---|---|
| **A_baseline** | PASS | 0.5625 | 4 | **yes** | 0.23 | **5,348.23** |
| B_equal | PASS | 0.3125 | 1 | **no** | — | — |
| C_separation_proportional | FAIL | 0.0000 | 0 | **no** | — | — |
| D_drop_flagged | FAIL | 0.1250 | 1 | **no** | — | — |
| E_drop_temporal | PASS | 0.5625 | 4 | yes | 0.26 | 5,348.23 |

**Three of five candidates are refused.** C and D fail the panel outright. B is
refused by the difficulty gate alone — it passes the panel and still loses three
of the four hard negatives from the positive range. Without the tightened gate B
would have been scored and compared.

**Selected: A_baseline. The incumbent is retained.** A and E tie at *exactly*
5,348.23 and the tie breaks to A: equal `positives_below_max_negative`, then
incumbent over change. No candidate beat A, and none was made to.

**E tying A exactly is the third independent confirmation that `temporal_burst`
is redundant.** The ablation found removing it changed no held-out metric; it
also changes no expected-loss figure — only the threshold that reaches it, 0.23
against 0.26. That is now three measurements agreeing, and it strengthens
`deferred_decisions.md` D1 rather than resolving it: A is retained because
nothing beat it, not because the weight was validated.

**Against the trivial policy.** Flag-everything costs 35,009.29 on validation at
a 100% review rate; A costs 5,348.23 at a 29.03% review rate, an **84.7%**
improvement. The 88:1 FN/FP ratio did not produce a degenerate optimum.

### Sensitivity (required by §4)

| | FP 0.01 | FP 0.02 | FP 0.05 |
|---|---|---|---|
| **FN 0.50** | A — 5,174.12 | A — 5,348.23 | A — 5,870.58 |
| **FN 0.75** | A — 5,174.12 | A — 5,348.23 | A — 5,870.58 |
| **FN 1.00** | A — 5,174.12 | A — 5,348.23 | A — 5,870.58 |

The winner is stable across the whole grid, and A ties E exactly in every cell.

**`FN_ABSORBED_FRACTION` has no effect at all, and that is worth understanding
rather than glossing.** A's loss-minimising operating point has **fn = 0** — it
recovers every ring on validation — so `C_fn` is multiplied by zero and never
enters the total. A's expected loss is entirely false-positive and review cost:
tp 8, fp 1, fn 0, tn 22, review cost 4,500.00 of the 5,348.23 total. The
consequence is that **this cost model is currently insensitive to the input it
was mainly derived from.** It would start to bite on a harder split, a stricter
threshold, or a ring type the scorer misses — but on this data the FN cost is
doing no work, and any claim that the operating point is FN-cost-driven would be
false.

### Not done

Step 5, the single held-out read, has **not** been performed. The policy is
frozen and `evaluate_frozen_policy()` will permit exactly one read when approved.
