# Abstention / review-band protocol — frozen before any band is selected

**Status: RUN and CLOSED (re-frozen, Phase 11). Band `t_lo = 0.14`, `t_hi = 0.23`
selected on validation behind the coverage gate, frozen to
`out/abstention_policy.json`, and the held-out split read **once** through
`evaluate_frozen_abstention_policy()` — see §8 / §8b. No further read is
permitted under this record; any future comparison needs its own frozen
protocol.**

Re-run because Phase 10/11 re-froze the scorer (`weight_search_protocol.md`,
`D_drop_flagged` folded into the new `A_baseline`) and its binary threshold
moved from 0.23 to 0.14 — everything below is against the new benchmark.

This layers a second decision policy on top of the already-frozen A_baseline
scorer and its already-frozen binary threshold (0.14, `weight_search_protocol.md`
§8). Neither the scorer's eight weights nor the binary threshold's own reported
numbers — F1 0.7619, expected loss 8,041.65 — are reopened, touched, or
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

**Not selected here:** the scorer, its eight weights, the generator, the
ground-truth rule, the split, or the binary threshold 0.14. That threshold
remains the frozen record for the *binary* policy and is quoted nowhere in this
document as something this protocol chose.

**0.14 is not treated as an immutable Allow boundary in this model.** `t_lo`
and `t_hi` are both free parameters, searched independently over the full
[0.00, 1.00] grid. Pinning `t_lo` to 0.14 was considered and rejected during
design (see the earlier design proposal) specifically because it would bake in
an assumption — that 0.14 remains the right Allow boundary — that the search
can just as easily confirm on its own. §8 reports where the free search
actually lands relative to 0.14; that placement is a *result*, not a
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
values — 76,985.91 / 308.33 / 500.00 — recomputed on the same design split, not
re-derived. No new cost input is introduced.

**The binary collapse.** At `t_lo == t_hi`, Review is empty by construction and
this formula is bit-for-bit `costmodel.expected_loss()`: Allow is the old
negative-predicted set, Escalate is the old positive-predicted set. This is
verified as a permanent assertion in `tests/test_riskmesh.py` — `t_lo = t_hi =
0.14` must reproduce validation expected loss 8,849.98 exactly — not merely
checked once while writing this document. A future change to either formula
that breaks the equivalence fails that test.

**D3 is resolved, not carried forward, as of Phase 10.** `deferred_decisions.md`
D3 used to record that `C_fp`'s own derivation already included one review
cost, and the Escalate-negative line above added a second, separate
`C_review` — an escalated false positive was charged a review twice. Phase 10
fixed `derive_costs()` to drop the embedded review term from `C_fp`, so it is
now friction-only (308.33, no review component), and the generic
`(tp+fp)*C_review` term is the *only* place a review cost is charged, for
every flagged component. There is one cost model now, not two under separate
accountings, and this protocol's formula needed no change to inherit the fix
— it already reused `derive_costs()`'s output rather than reimplementing it.

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
difficulty gates in `costmodel.py` are evaluated on design: more data (73 rows
against 40), less small-sample noise in the coverage measurement, and the same
failure mode being guarded against (`bugs.md` L2: an optimiser finding the
cheapest way to move a number rather than the honest way — here, "review
almost everything" rather than "discriminate better", since `C_review` (500)
is far cheaper than `C_fn` (74,645) or `C_fp` (848) once Review waives both).

**0.25 is a business-policy choice, not a data fact.** Nothing in this
benchmark derives it; it is a judgement about how much analyst throughput a
review band may reasonably consume. It is set well above what the design-time
exploration found the unconstrained optimum to actually need (17.5% of
validation, 13.7% of design — §8), so it does not bind on this run. It exists
as a structural backstop against a *different* result on a future run, a
different generator draw, or a harder ring type — not because today's numbers
demanded it. If it needs to move, that is a decision for whoever revisits this
protocol, made explicitly, the same way `MIN_HARD_NEGATIVES_IN_RANGE` and
`MIN_POSITIVES_BELOW_MAX_NEGATIVE` are absolute rather than a margin from
whatever the incumbent currently does.

---

## 5. What was predicted, and what happened

Stated before running anything, so the record cannot be read backwards.

**Prediction (Phase 11 re-run, restated before this run):** the same structural
argument as the original run applies again — `C_review` (500) is far cheaper
than `C_fn` (76,986) or `C_fp` (308), and Review waives both, so an
unconstrained sweep should still prefer routing almost everything to Review
rather than risking either automated-decision cost.

**Result: the prediction was wrong again, for the same structural reason.**
`A_baseline` (== the re-frozen `D_drop_flagged` weight vector) already has
**zero missed positives at 0.14** on both validation (40 rows) and train (33
rows) — `fn = 0` throughout, the same fact `weight_search_protocol.md` §8
records for the binary policy. Widening Review downward past 0.14 therefore
still only adds review cost with nothing to rescue. Above 0.14, the search
this time finds it worthwhile to pull several negatives into Review (`t_hi`
lands at 0.23, not immediately above `t_lo` as before) — see §8's band. The
mechanism is the same as originally reported: this is a structural property
of a benchmark this scorer already achieves zero-FN recall on, not evidence
that review is cheap enough to matter regardless of recall.

**This does not retire the gate.** A narrow-ish optimum today, on 40 validation
rows, is not a proof that a different draw, a harder ring type, or the real
held-out split behaves the same way. The gate stays as a structural backstop
regardless of whether it binds on this particular run — the same reasoning
that kept `costmodel.py`'s difficulty gates even though only one of the two
candidates they were built to catch turned out to need them.

---

## 6. What the selected band means, and does not mean

Whatever `(t_lo, t_hi)` `select_abstention_band()` returns in §8 is **optimal
under this protocol's Phase-1 assumptions and the 0.25 review-coverage
cap, evaluated on 40 validation components** — not a claimed correct fraud
threshold, and not evidence that this exact band generalises. In particular:

- It depends on the perfect-analyst-review assumption in §3, which is asserted,
  not measured.
- It depends on `MAX_REVIEW_RATE = 0.25`, a business choice, not a data fact.
- It is fit to validation's specific error pattern. Unlike the original run,
  a design-split diagnostic finds train's own ambiguous cases fully inside the
  selected band this time (zero Escalate false positives on train outside
  `[0.14, 0.23)`) — that is a property of this particular draw, not a
  guarantee, and is exactly why the held-out read in §7 matters and cannot be
  skipped or predicted from this table.

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
real code against the Phase 10/11 benchmark: 3,726 bands passed the coverage
gate out of 5,151 tried (1,425 refused), `t_lo = 0.14`, `t_hi = 0.23`, panel
PASS.

| | value |
|---|---|
| selected band | `t_lo = 0.14`, `t_hi = 0.23` |
| validation expected loss | **7,308.33** (binary A_baseline: 8,849.98) |
| validation review rate | **17.5%** (7 of 40: 2 positive, 5 negative-family) |
| design review rate (the gated quantity) | **13.7%** (10 of 73, `<= 0.25` cap; 7 of the 8 negatives are family) |
| validation confusion | Allow 26 (0 missed positives), Review 7, Escalate 7 (6 TP, 1 FP) |
| bands considered / refused by coverage | 3,726 / 1,425 (of 5,151 total) |

**Where the free search landed relative to the frozen binary threshold:**
`t_lo` came out exactly at 0.14 — the same number `weight_search_protocol.md`
froze for the binary policy — without being told to, reproducing the same
result the original run reported at 0.23. §5 explains why: `A_baseline`
already has zero missed positives at 0.14 on both validation and train, so a
free search has no incentive to move the Allow boundary. Unlike the original
run, `t_hi` this time lands meaningfully above `t_lo` (0.23, not 0.24) and the
band pulls in 5 negatives rather than 1 — the search found more headroom to
work with on this draw, not less. This is a result, not a constraint the code
enforces; a different generator draw could move it again.

**Reading this table**: it is the design-side confirmation this protocol
exists to demonstrate — a coded, gated, structurally-frozen search reproduces
the hand-checked design proposal — not a claim about held-out performance.

---

## 8b. The single permitted held-out read (taken, once)

Through `evaluate_frozen_abstention_policy()`, with `t_lo`/`t_hi` read back
**from** `out/abstention_policy.json` rather than recomputed. 32 test
components: 8 positive, 24 negative, 8 of the negatives carrying a family
cluster.

| | validation (selection) | **held out** |
|---|---|---|
| expected loss | 7,308.33 | **6,808.33** |
| review rate | 17.5% (7/40) | **15.6%** (5/32) |
| Allow | 26 (0 positives) | **19** (0 positives) |
| Review | 7 (2 pos, 5 neg-family) | **5** (1 pos, 4 neg — all 4 family) |
| Escalate | 7 (6 TP, 1 FP) | **8** (7 TP, **1 FP**) |

**Against the binary baseline on the identical test rows** (threshold 0.14,
`weight_search_protocol.md` §8's frozen result): binary expected loss
**8,041.65** with tp 8 / fp 5 / fn 0 / tn 19, against the three-way's
**6,808.33** — a delta of **−1,233.32**, a **15.3%** reduction.

**The structural result is weaker this time than the original run, and that
is reported plainly rather than smoothed over.** Four of the binary policy's
five held-out false positives — family components scoring 0.1998, 0.2202,
0.2215, 0.2253 — fall inside the review band and are waived. **The fifth,
`c_a00744` at 0.2593, does not** — it clears `t_hi` and is escalated as a
false positive under the three-way policy too. Unlike the original run, the
three-way band does **not** eliminate escalated false positives entirely:
`escalate_negative = 1`, not 0. `allow_missed_positives = 0` on both splits, so
no ring is missed at the Allow tier, and one ring is deferred to Review rather
than escalated (`review_positive = 1`).

**Tier metrics, stated so the three-way case is not read as a binary one.**
Escalate-tier precision **0.8750** (7/8) and escalate-tier FPR **0.0417**
(1/24), against the binary policy's 0.6154 and 0.2083 — still a clear
improvement on both axes, just not a clean sweep. Escalate-tier recall is
**0.8750** (7 of 8 rings) — the remaining ring (score 0.2018) is deferred to
review, not missed. Counting a deferred ring as caught-but-unconfirmed gives
8/8; that figure is **not** a detection claim and must not be quoted as
recall 1.0 without the qualifier.

**The move against validation is sample variance, in the opposite direction
from the original run, and was called in advance as a possibility either way.**
Held-out 6,808.33 against validation's 7,308.33 is a **6.8% improvement**, not
a regression — the same small-sample mechanism as the binary policy's own
8,849.98 → 8,041.65 move (also a slight improvement this run, unlike the
original run's 76% regression): 24-32 rows per split, where one component
moves the total materially and post-D3 `C_fp` (308.33, friction only) moves it
by less per component than the old double-charged 848.23 did. The review band
caught 5 test cases against design's 10 — a smaller fraction, not the same
fraction — and there is no structural finding in that gap beyond variance.
**Neither the validation nor the held-out figure should be quoted as "the"
policy's cost** — both are honest reads of small, different samples.

**D3 is resolved, not a caveat, as of Phase 10.** The original run had to
report two figures for its improvement (36.1% as computed, 18.8% under a
hypothetical D3-corrected cost model) because `C_fp` double-charged a review at
the time. `derive_costs()` now charges the review once, so the **15.3%**
figure above is the only number — there is no second accounting to reconcile
it against.

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
* The binary-collapse test (t_lo = t_hi = 0.14 reproduces 8,849.98) removed,
  weakened, or skipped.

If any of these happens, the protocol is void and selection is re-run from a
new frozen record.
