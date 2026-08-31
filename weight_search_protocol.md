# Weight-search protocol — frozen before any candidate is scored

**Status: RUN and CLOSED (re-frozen, Phase 11). Outcome in §8 — `D_drop_flagged`
won.** Phase 10 added the hybrid pool-funded ring mechanism, the 8th signal
(`instrument_pool_concentration`), and fixed the D3 cost-model double-charge —
which moved the config fingerprint and made every number below stale, so this
protocol was re-run against the new benchmark from scratch, unchanged rules,
same five candidates. Unlike the original run, `A_baseline` did **not** win
outright: `D_drop_flagged` (which zeros `instrument_sharing` and
`merchant_concentration`, RISK-004's and RISK-002's flagged signals) tied
`A_baseline` exactly on validation expected loss and won the tie-break on
`positives_below_max_negative`. Per this document's own §5 rule and
`task_today.md`'s "one subtlety" clause, the winning weight vector was folded
back into `Config()._default_weights()` and the entire search was re-run once
more against that new incumbent — which reproduced the same winner, now
labelled `A_baseline` again, a fixed point reached in exactly one extra
iteration. The held-out split **has been read, once**, through
`evaluate_frozen_policy()` — see §8's "Step 5" table (F1 0.7619, expected loss
8,041.65 at threshold 0.14). Per §5 rule 6 and §7, no second read is permitted
under this record; any future comparison needs its own frozen protocol.

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
| `C_fn` | **76,985.91** | median ring-component exposure (INR 76,985.91) × `FN_ABSORBED_FRACTION` 1.00 |
| `C_fp` | **308.33** | `FP_FRICTION_RATE` 0.02 × median negative-component exposure (15,416.44) — friction only, no embedded review term (Phase 10 fixed `deferred_decisions.md` D3: the generic `(TP+FP) × C_review` term already prices one review per flagged component) |

Data behind these (Phase 10/11 benchmark): 16 positive and 57 negative design
components; median ring exposure 76,985.91; median negative exposure 15,416.44.
No round numbers are presented without a derivation.

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

`C_fn / C_fp` is **249.7:1** (higher than the original run's 88:1, since Phase 10
fixed D3 and dropped the embedded review term from `C_fp`, shrinking it). At
that ratio the loss-minimising threshold will be very low and may collapse to
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

## 8. Outcome — run on validation only, held-out untouched

Record: `out/weight_policy.json`. Costs re-derived on the Phase 10 benchmark:
`C_review` 500.00, `C_fn` 76,985.91 (median ring exposure), `C_fp` 308.33
(friction only, D3 fixed — no embedded review term), ratio 249.7:1.

**First pass**, run with the pre-Phase-11 `Config()._default_weights()` still
in force (fingerprint `0a3434da04b81aa9`):

| policy | panel | pbmn | hard-neg | feasible | threshold | expected loss |
|---|---|---|---|---|---|---|
| A_baseline | PASS | 0.5625 | 9 | yes | 0.14 | 8,849.98 |
| B_equal | PASS | 0.2500 | 8 | **no** | — | — |
| C_separation_proportional | PASS | 0.5625 | 8 | yes | 0.08 | 14,508.29 |
| **D_drop_flagged** | PASS | 0.6250 | 6 | **yes** | 0.14 | **8,849.98** |
| E_drop_temporal | PASS | 0.5625 | 10 | yes | 0.16 | 10,466.64 |

**Only one of five is refused this time — B_equal**, on the difficulty gate
alone (pbmn 0.2500 < 0.45). Unlike the original run, C and D both clear the
panel outright: the new `instrument_pool_concentration` signal carries enough
of the instrument dimension that C's separation-proportional weighting no
longer collapses the benchmark, and D no longer removes all instrument-axis
signal (RISK-004's fix, not a gate regression — see `bugs.md` RISK-004 and
`tests/test_riskmesh.py` test_19).

**A and D tie exactly at 8,849.98 (identical confusion: tp 8, fp 6, fn 0,
tn 26) and the tie breaks to D**, not to A: `positives_below_max_negative`
0.6250 (D) beats 0.5625 (A), and that comparison is checked *before* the
incumbent tie-break — the protocol never reaches "prefer A" because D already
wins on the sharper difficulty margin. **This is the first run in this
project where the incumbent tie-break did not fire.**

**Per §5 rule 3 and `task_today.md`'s "one subtlety" clause**, `D_drop_flagged`
winning means `A_baseline` (which is *defined* as `Config()._default_weights()`,
per `costmodel.policy_a_baseline()`) is no longer what the pipeline actually
scores with. The winning vector — device_sharing 0.2716, temporal_burst
0.3086, instrument_pool_concentration 0.1481, failure_refund_rate 0.1481,
account_newness 0.1235, with `ip_sharing`, `instrument_sharing` and
`merchant_concentration` all at 0.00 — was written into
`Config()._default_weights()`, and the **entire search was re-run from scratch**
against that new incumbent (new fingerprint `c3ee14627c2c2ce2`, since the
weights are part of the fingerprint).

**Second pass, against the new incumbent — the fixed point:**

| policy | panel | pbmn | hard-neg | feasible | threshold | expected loss |
|---|---|---|---|---|---|---|
| **A_baseline** | PASS | 0.6250 | 6 | **yes** | 0.14 | **8,849.98** |
| B_equal | PASS | 0.3750 | 6 | **no** | — | — |
| C_separation_proportional | PASS | 0.5625 | 8 | yes | 0.08 | 14,508.29 |
| D_drop_flagged | PASS | 0.6250 | 6 | yes | 0.14 | 8,849.98 |
| E_drop_temporal | PASS | 0.4375 | 10 | **no** | — | — |

**Converged in exactly one extra iteration, as predicted.** `D_drop_flagged`
now zeros two signals that were *already* zero in the new `A_baseline`, so it
is a no-op — the two rows are identical by construction and the tie resolves
to `A_baseline` on the incumbent tie-break this time, because there is no
longer a sharper `positives_below_max_negative` to prefer. **B_equal remains
refused. E_drop_temporal is newly refused** (pbmn 0.4375 < 0.45) — under the
new weight vector, dropping `temporal_burst` no longer clears the difficulty
gate, which is a different outcome from the original run's E tying A exactly.
This is a new, weaker measurement on D1 (`deferred_decisions.md`): `E` is no
longer even a feasible comparison point under the current weights, so D1
cannot be resolved this way either.

**Selected: A_baseline (== the former D_drop_flagged), at threshold 0.14,
validation expected loss 8,849.98.** The search does not need a third pass:
nothing about the second pass's winner or its own candidate set changed
between passes two and three would produce, since `A_baseline` already equals
what `D_drop_flagged` computes from it (zeroing two already-zero weights).

**Against the trivial policy.** Flag-everything costs 29,866.56 on validation
at a 100% review rate; the winner costs 8,849.98 at a 35.00% review rate, a
**70.4%** improvement.

### Sensitivity (required by §4)

| | FP 0.01 | FP 0.02 | FP 0.05 |
|---|---|---|---|
| **FN 0.50** | A — 7,924.96 | A — 8,849.98 | A — 11,624.92 |
| **FN 0.75** | A — 7,924.96 | A — 8,849.98 | A — 11,624.92 |
| **FN 1.00** | A — 7,924.96 | A — 8,849.98 | A — 11,624.92 |

The winner is stable across the whole grid — `A_baseline` in every cell, tying
`D_drop_flagged` exactly in every cell for the reason above (D is now a no-op
on the current weights).

**`FN_ABSORBED_FRACTION` still has no effect at all**, for the same reason as
the original run: the winner's loss-minimising operating point has **fn = 0**
on validation (tp 8, fp 6, fn 0, tn 26), so `C_fn` is multiplied by zero and
never enters the total. The cost model remains insensitive to the input it was
mainly derived from; the false-positive and review terms are still doing all
the work.

### Step 5 — the single held-out read (done, once)

Taken through `evaluate_frozen_policy()` after the policy was frozen.
`A_baseline` at the frozen threshold 0.14, on 32 test components:

| | validation (selection) | held out |
|---|---|---|
| precision | — | **0.6154** |
| recall | — | **1.0000** |
| F1 | — | **0.7619** |
| FPR | — | **0.2083** |
| ring recovery | — | **8/8 (100%)** |
| confusion | tp 8, fp 6, fn 0, tn 26 | tp 8, **fp 5**, fn 0, tn 19 |
| expected loss | 8,849.98 | **8,041.65** |
| review rate | 0.3500 | 0.4062 |

Account level: precision 0.6452, recall 1.0000, F1 0.7843, FPR 0.4231.

**Held-out expected loss is 9.1% LOWER than the validation figure this time**
— the opposite direction from the original run's 76% regression. This is not
evidence the policy generalises better; it is the same small-sample variance
in the other direction: 6 false positives on 32 validation negatives against
5 on 24 test negatives, and at `C_fp` 308.33 (friction-only, post-D3) each
false positive moves the total far less than it used to under the old
double-charged `C_fp` of 848.23. **Neither figure should be quoted as "the"
system cost** — both are the honest read of two different 30-ish-row samples.

**All five held-out false positives are family components. Zero are
background.** Same structural finding as the original run: the residual error
is entirely the hard negatives the benchmark was built to produce, which
remains the argument for the abstention band rather than for more weight
tuning.

Against flag-everything on test (23,399.92 at a 100% review rate), the winner
improves by **65.6%** — close to, and in the same direction as, validation's
70.4%.

**No further read is permitted.** Any future comparison needs a new frozen record.
