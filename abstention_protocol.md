# Abstention / review-band protocol — frozen before any band is selected

**Status: RUN and CLOSED. Band `t_lo = 0.23`, `t_hi = 0.33` selected on
validation behind the coverage gate, frozen to `out/abstention_policy.json`,
and the held-out split read **once** through
`evaluate_frozen_abstention_policy()` — see §8. No further read is permitted
under this record; any future comparison needs its own frozen protocol.**

This layers a second decision policy on top of the already-frozen A_baseline
scorer and its already-frozen binary threshold (0.23, `weight_search_protocol.md`
§8). Neither the scorer's seven weights nor the binary threshold's own reported
numbers — F1 0.8000, expected loss 9,392.92 — are reopened, touched, or
re-derived by anything in this document. This protocol governs a *different*
question: given the same scores, where should a three-way allow/review/escalate
split put its two boundaries, and how is that choice frozen before test data is
read, the same way every other selection in this project has been.

Code: `riskmesh/abstention.py`. Evidence motivating a review band at all:
`implementation_plan.md` "Why abstention comes before XGBoost" — every held-out
error under A_baseline is a hard-negative family component, zero are
background, which is the shape of problem abstention solves and a threshold
alone does not.

---

## 1. What is being selected, and what is not

**Selected:** two score thresholds, `t_lo <= t_hi`, defining

```
score < t_lo           -> Allow      (no review, no action)
t_lo <= score < t_hi    -> Review     (one manual review; see §3's assumption)
score >= t_hi           -> Escalate   (same handling as the binary "flag")
```

**Not selected here:** the scorer, its seven weights, the generator, the
ground-truth rule, the split, or the binary threshold 0.23. That threshold
remains the frozen record for the *binary* policy and is quoted nowhere in this
document as something this protocol chose.

**0.23 is not treated as an immutable Allow boundary in this model.** `t_lo`
and `t_hi` are both free parameters, searched independently over the full
[0.00, 1.00] grid. Pinning `t_lo` to 0.23 was considered and rejected during
design (see the earlier design proposal) specifically because it would bake in
an assumption — that 0.23 remains the right Allow boundary — that the search
can just as easily confirm on its own. §8 reports where the free search
actually lands relative to 0.23; that placement is a *result*, not a
constraint.

---

## 2. The mechanism

`riskmesh/abstention.py`'s `three_way_stats()` computes, for one `(t_lo, t_hi)`:

```
Allow,    actual ring      -> C_fn                  (missed entirely)
Allow,    actual negative  -> 0
Review,   either label     -> C_review               (one review; see §3)
Escalate, actual ring      -> C_review               (TP -- same as the binary policy)
Escalate, actual negative  -> C_fp + C_review         (FP -- same as the binary policy)
```

`C_fn`, `C_fp`, `C_review` are exactly `costmodel.derive_costs()`'s frozen
values — 74,645.29 / 848.23 / 500.00 — recomputed on the same design split, not
re-derived. No new cost input is introduced.

**The binary collapse.** At `t_lo == t_hi`, Review is empty by construction and
this formula is bit-for-bit `costmodel.expected_loss()`: Allow is the old
negative-predicted set, Escalate is the old positive-predicted set. This is
verified as a permanent assertion in `tests/test_riskmesh.py` — `t_lo = t_hi =
0.23` must reproduce validation expected loss 5,348.23 exactly — not merely
checked once while writing this document. A future change to either formula
that breaks the equivalence fails that test.

**A known, carried-forward quirk in the costs this formula reuses**, logged as
`deferred_decisions.md` D3: `C_fp`'s own derivation already includes one review
cost, and the Escalate-negative line above adds a second, separate
`C_review` — an escalated false positive is charged a review twice, once inside
`C_fp` and once through the generic per-flag review term. This is carried
forward unchanged from `costmodel.expected_loss()`, for the same reason that
formula has not been touched: fixing it would move the already-frozen 5,348.23 /
9,392.92 baseline without a new frozen record. D3 is owned by the cost-model
stage, same as D1 and D2, not by this protocol.

---

## 3. The one new assumption

**A component routed to Review is resolved correctly by the analyst before any
automated action is taken.** This is why Review costs exactly one review and
neither `C_fp` nor `C_fn` — it is the entire mechanism by which a review band
can reduce expected loss relative to a binary policy.

**This is a Phase-1 cost-model assumption, not an empirical measurement.** The
dataset contains nothing that could inform an analyst error rate, the same way
it contained nothing that could inform `ANALYST_MINUTES_PER_COMPONENT` in
`costmodel.py`. It is named and flagged for the same reason those constants
are: so a reader encounters it as a stated premise, not something to discover
by reverse-engineering the formula. A partial-credit version — an explicit
analyst accuracy rate below 1.0 — is future work and is not implemented here.

---

## 4. The gate — structural, not conventional

A band that reviews too much of the design split is not a worse candidate. It
does not receive an expected-loss figure that is later discarded; there is no
figure. Mirrors `costmodel.py`'s `PanelGateFailure` / `DifficultyGateFailure`
exactly, in a new sibling exception:

| gate | bound | enforced by |
|---|---|---|
| non-triviality panel | verdict `PASS` | `PanelGateFailure` (reused from `costmodel.py`) |
| review-band coverage | `<= 0.25` on **design** (train+validation) | `ReviewBandGateFailure` |

**Panel PASS is checked once, not per band.** The scorer and its weights are
unchanged from the already-gated A_baseline, so the panel verdict does not vary
with `(t_lo, t_hi)` — recomputing it per candidate band would be redundant, not
more rigorous. It is asserted as a precondition before the sweep begins, and
`select_abstention_band()` raises the same `PanelGateFailure` `costmodel.py`
uses if it is somehow not PASS, on the theory that a failure here would mean
something upstream changed the scorer or the data, not the band.

**`MAX_REVIEW_RATE = 0.25`, on design coverage.** Declared here, before any
band was scored — not fitted to whatever the search happened to find. On
design (train+validation), not validation alone, for the same reason the two
difficulty gates in `costmodel.py` are evaluated on design: more data (69 rows
against 31), less small-sample noise in the coverage measurement, and the same
failure mode being guarded against (`bugs.md` L2: an optimiser finding the
cheapest way to move a number rather than the honest way — here, "review
almost everything" rather than "discriminate better", since `C_review` (500)
is far cheaper than `C_fn` (74,645) or `C_fp` (848) once Review waives both).

**0.25 is a business-policy choice, not a data fact.** Nothing in this
benchmark derives it; it is a judgement about how much analyst throughput a
review band may reasonably consume. It is set well above what the design-time
exploration found the unconstrained optimum to actually need (6.45% of
validation, 10.14% of design — §8), so it does not bind on this run. It exists
as a structural backstop against a *different* result on a future run, a
different generator draw, or a harder ring type — not because today's numbers
demanded it. If it needs to move, that is a decision for whoever revisits this
protocol, made explicitly, the same way `MIN_HARD_NEGATIVES_IN_RANGE` and
`MIN_POSITIVES_BELOW_MAX_NEGATIVE` are absolute rather than a margin from
whatever the incumbent currently does.

---

## 5. What was predicted, and what happened

Stated before running anything, so the record cannot be read backwards.

**Prediction:** an unconstrained sweep would degenerate toward "review
everything." `C_review` (500) is far cheaper than `C_fn` (74,645) or `C_fp`
(848), and Review waives both, so an optimiser should prefer routing almost
everything to Review rather than risking either automated-decision cost.

**Result: the prediction was wrong, and the reason is diagnostic, not
incidental.** A_baseline already has **zero missed positives at 0.23** on both
validation and train (`fn = 0` throughout, the same fact
`weight_search_protocol.md` §8 already recorded for the binary policy).
Widening Review downward past 0.23 therefore only adds review cost with
nothing to rescue — there is no missed-positive cost sitting in Allow for a
wider band to recover. And above 0.23, the only negative worth pulling into
Review is the handful of components already near the boundary; widening `t_hi`
further only pulls already-cheap true positives into Review at no cost change
(500 either way), which does not move the optimum. The unconstrained search
finds a narrow band for a structural reason specific to this benchmark's
current recall, not because review is expensive in this cost model — it is
not. This is reported as a refuted prediction, not omitted, on the same
principle every experiment record in this project uses.

**This does not retire the gate.** A narrow optimum today, on 31 validation
rows, is not a proof that a different draw, a harder ring type, or the real
held-out split behaves the same way. The gate stays as a structural backstop
regardless of whether it binds on this particular run — the same reasoning
that kept `costmodel.py`'s difficulty gates even though only one of the two
candidates they were built to catch turned out to need them.

---

## 6. What the selected band means, and does not mean

Whatever `(t_lo, t_hi)` `select_abstention_band()` returns in §8 is **optimal
under this protocol's Phase-1 assumptions and the 0.25 review-coverage
cap, evaluated on 31 validation components** — not a claimed correct fraud
threshold, and not evidence that this exact band generalises. In particular:

- It depends on the perfect-analyst-review assumption in §3, which is asserted,
  not measured.
- It depends on `MAX_REVIEW_RATE = 0.25`, a business choice, not a data fact.
- It is fit to validation's specific error pattern (currently: one ambiguous
  family component near the boundary). A design-split diagnostic already shows
  this band does **not** fully generalise to train's own ambiguous cases —
  train retains one Escalate false positive outside the validation-selected
  band. That gap is expected (the objective only ever optimises validation,
  same as `select_threshold()` always has) and is exactly why the held-out read
  in §7 matters and cannot be skipped or predicted from this table.

Report the band this way — "optimal under Phase-1 assumptions and the review
cap" — everywhere it is quoted. Do not report it as "the threshold at which
family accounts stop looking like fraud."

---

## 7. Procedure — objective hierarchy, in order

1. **No test access before freeze.** `evaluate_frozen_abstention_policy()`
   raises `AbstentionPolicyNotFrozen` unless `out/abstention_policy.json`
   already exists on disk. Structurally impossible to reach a test row through
   the public API before that file is written, the same guarantee
   `costmodel.evaluate_frozen_policy()` gives the binary policy.
2. **Review-rate feasibility gate**, per candidate `(t_lo, t_hi)`, evaluated on
   design (train+validation) coverage: `review_rate <= 0.25`, else the band is
   not a candidate (§4).
3. **Existing integrity-panel constraint**, checked once against the design
   split before the sweep begins (§4) — inherited from the already-gated
   A_baseline, not re-litigated here.
4. **Minimise expected loss**, per feasible candidate band, evaluated on
   validation only (§2's formula).
5. **Freeze** the winning band, its validation expected loss, its design
   review-rate, and the full search's `bands_considered` /
   `bands_refused_by_coverage` counts to `out/abstention_policy.json`, *before*
   any test row is read.
6. **Read the held-out split once**, through
   `evaluate_frozen_abstention_policy()`, and report precision/recall/coverage
   for all three tiers on test. No second read. **Taken — see §8b.**

---

## 8. Outcome — run on design data only, held-out split untouched

Record: `out/abstention_policy.json`. `select_abstention_band()` run against
real code, not the interactive design-stage analysis that produced this
protocol's numbers in the first place — and it reproduced them exactly: 2,992
bands passed the coverage gate out of 5,151 tried (2,159 refused), `t_lo =
0.23`, `t_hi = 0.33`, panel PASS.

| | value |
|---|---|
| selected band | `t_lo = 0.23`, `t_hi = 0.33` |
| validation expected loss | **4,500.00** (binary A_baseline: 5,348.23) |
| validation review rate | **6.45%** (2 of 31: 1 positive, 1 negative-family) |
| design review rate (the gated quantity) | **10.14%** (7 of 69, `<= 0.25` cap; 3 of the 7 are family) |
| validation confusion | Allow 22 (0 missed positives), Review 2, Escalate 7 (7 TP, 0 FP) |
| bands considered / refused by coverage | 2,992 / 2,159 (of 5,151 total) |

**Where the free search landed relative to the frozen binary threshold:**
`t_lo` came out exactly at 0.23 — the same number `weight_search_protocol.md`
froze for the binary policy — without being told to. §5 explains why: A_baseline
already has zero missed positives at 0.23 on both validation and train, so a
free search has no incentive to move the Allow boundary. This is a result, not
a constraint the code enforces; a different generator draw could move it, and
this section's job is to report what happened, not to expect it.

**Reading this table**: it is the design-side confirmation this protocol
exists to demonstrate — a coded, gated, structurally-frozen search reproduces
the hand-checked design proposal — not a claim about held-out performance.

---

## 8b. The single permitted held-out read (taken, once)

Through `evaluate_frozen_abstention_policy()`, with `t_lo`/`t_hi` read back
**from** `out/abstention_policy.json` rather than recomputed. 31 test
components: 8 positive, 23 negative, 8 of the negatives carrying a family
cluster.

| | validation (selection) | **held out** |
|---|---|---|
| expected loss | 4,500.00 | **6,000.00** |
| review rate | 6.45% (2/31) | **19.35%** (6/31) |
| Allow | 22 (0 positives) | **19** (0 positives) |
| Review | 2 (1 pos, 1 neg-family) | **6** (2 pos, 4 neg — all 4 family) |
| Escalate | 7 (7 TP, 0 FP) | **6** (6 TP, **0 FP**) |

**Against the binary baseline on the identical test rows** (threshold 0.23,
`weight_search_protocol.md` §8's frozen result): binary expected loss
**9,392.92** with tp 8 / fp 4 / fn 0 / tn 19, against the three-way's
**6,000.00** — a delta of **−3,392.92**, a 36.1% reduction.

**The structural result, and it is the one the design predicted.** All four of
the binary policy's held-out false positives — family components scoring
0.2503, 0.2609, 0.2981, 0.3201 — fall inside the review band. The three-way
policy escalates **zero** false positives; every remaining escalation (6 of 6)
is a true ring. `implementation_plan.md` argued abstention before XGBoost on
exactly the grounds that "every held-out error is a hard negative"; those four
components are the errors, and the band catches all four. Nothing is
auto-allowed: `allow_missed_positives = 0`, so no ring is missed at the Allow
tier on either split.

**Tier metrics, stated so the three-way case is not read as a binary one.**
Escalate-tier precision **1.0000** (6/6) and escalate-tier FPR **0.0000**
(0/23), against the binary policy's 0.6667 and 0.1739. Escalate-tier recall is
**0.7500** (6 of 8 rings) — the other two rings (scores 0.2866, 0.3068) are
deferred to review, not missed. Counting a deferred ring as caught-but-
unconfirmed gives 8/8; that figure is **not** a detection claim and must not be
quoted as recall 1.0 without the qualifier.

**The regression against validation is sample variance, and was called in
advance.** Held-out 6,000.00 against validation's 4,500.00 is +33.3%, the same
direction and the same cause as the binary policy's 5,348.23 → 9,392.92 (+76%):
23 negatives per split, where one component moves the total materially. The
review band caught 6 test cases (not zero) and caught nothing categorically
absent from design — design review held 4 positives and 3 negatives, test holds
2 positives and 4 negatives, the same two kinds in a different mix. So there is
no structural finding here, only variance. **The validation figure 4,500.00
must not be quoted as the policy's cost.** Held-out review rate 19.35% is
likewise nearly double design's 10.14% while remaining under the 0.25 cap —
the cap is a design-time feasibility gate and was never applied to test, and
this is recorded as an observation, not as the gate passing on test.

**One caveat on the size of the improvement, flagged rather than banked.** The
36.1% figure is inflated by `deferred_decisions.md` D3: `C_fp` (848.23) already
contains one review cost (500.00), and the binary formula charges a second
review on every flag, so each avoided false-positive escalation appears to save
848.23 when the friction-only saving is 348.23. Under a D3-corrected cost model
the binary baseline would be 7,392.92 against the same unchanged three-way
6,000.00 — an improvement of **18.8%** rather than 36.1%. The direction and
sign are robust under either accounting; the magnitude roughly halves. Both
numbers are in the frozen record.

**No further read is permitted under this record.** Same rule as the ablation
and the weight search: any future comparison needs its own protocol frozen
before the read.

---

## 9. What would invalidate this protocol

Stated so it is falsifiable, mirroring `weight_search_protocol.md` §7:

* `t_lo` or `t_hi` chosen, adjusted, or re-swept after a held-out number is
  seen.
* `MAX_REVIEW_RATE` changed after seeing what band it would admit or refuse.
* The perfect-analyst-review assumption in §3 replaced with a measured rate
  derived from anything other than an explicit, separately-declared model.
* Any expected-loss number produced for a band that fails either gate.
* More than one held-out read.
* The binary-collapse test (t_lo = t_hi = 0.23 reproduces 5,348.23) removed,
  weakened, or skipped.

If any of these happens, the protocol is void and selection is re-run from a
new frozen record.
