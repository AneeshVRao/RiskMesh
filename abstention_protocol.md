# Abstention / review-band protocol — frozen before any band is selected

**Status: RUN and CLOSED (re-frozen, Phase 12). Band `t_lo = 0.18`, `t_hi = 0.18`
selected on validation behind the coverage gate — a degenerate, zero-width
band, identical to the binary policy on every row — frozen to
`out/abstention_policy.json`, and the held-out split read **once** through
`evaluate_frozen_abstention_policy()` — see §8 / §8b. No further read is
permitted under this record; any future comparison needs its own frozen
protocol.**

Re-run because Phase 12 fixed a real RNG-isolation bug in `_inject_rings`
(`riskmesh/generate.py`'s module comment; the instrument-mechanism branch let
the main stream's consumption depend on `is_hybrid`, a data-dependent branch)
which changes actual generator output without moving the config fingerprint —
so `weight_search_protocol.md`'s re-run against the corrected benchmark moved
the binary threshold from 0.14 to 0.18, and everything below is against that
new benchmark. (Phase 10/11 had already re-run this protocol once before, for
an unrelated reason — the scorer and its threshold moving from Phase 10's
generator and D3 cost-model changes.)

This layers a second decision policy on top of the already-frozen A_baseline
scorer and its already-frozen binary threshold (0.18, `weight_search_protocol.md`
§8). Neither the scorer's eight weights nor the binary threshold's own reported
numbers — F1 0.7778, expected loss 74,595.13 — are reopened, touched, or
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
ground-truth rule, the split, or the binary threshold 0.18. That threshold
remains the frozen record for the *binary* policy and is quoted nowhere in this
document as something this protocol chose.

**0.18 is not treated as an immutable Allow boundary in this model.** `t_lo`
and `t_hi` are both free parameters, searched independently over the full
[0.00, 1.00] grid. Pinning `t_lo` to the binary threshold was considered and
rejected during design (see the earlier design proposal) specifically because
it would bake in an assumption — that the binary threshold remains the right
Allow boundary — that the search can just as easily confirm on its own. §8
reports where the free search actually lands relative to 0.18 (the current
binary threshold); that placement is a *result*, not a constraint.

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
values — 68,399.84 / 398.43 / 500.00 — recomputed on the same design split, not
re-derived. No new cost input is introduced.

**The binary collapse.** At `t_lo == t_hi`, Review is empty by construction and
this formula is bit-for-bit `costmodel.expected_loss()`: Allow is the old
negative-predicted set, Escalate is the old positive-predicted set. This is
verified as a permanent assertion in `tests/test_riskmesh.py` — `t_lo = t_hi =
0.18` must reproduce validation expected loss 4,000.00 exactly — not merely
checked once while writing this document. A future change to either formula
that breaks the equivalence fails that test.

**D3 is resolved, not carried forward, as of Phase 10.** `deferred_decisions.md`
D3 used to record that `C_fp`'s own derivation already included one review
cost, and the Escalate-negative line above added a second, separate
`C_review` — an escalated false positive was charged a review twice. Phase 10
fixed `derive_costs()` to drop the embedded review term from `C_fp`, so it is
now friction-only (398.43, no review component), and the generic
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
difficulty gates in `costmodel.py` are evaluated on design: more data (69 rows
against 31), less small-sample noise in the coverage measurement, and the same
failure mode being guarded against (`bugs.md` L2: an optimiser finding the
cheapest way to move a number rather than the honest way — here, "review
almost everything" rather than "discriminate better". Post-D3, `C_review`
(500.00) is no longer far cheaper than both: it remains far cheaper than
`C_fn` (68,399.84), but `C_fp` is now friction-only and *smaller* than
`C_review` (398.43 < 500.00) -- the pre-D3 relationship this gate's rationale
used to assume is inverted for the false-positive side. The gate exists
regardless, because the `C_fn` side of the argument alone is enough to make
"review almost everything" the cheap way to move the number whenever a design
draw has any positives near the boundary; see §5 for what this run's search
actually found).

**0.25 is a business-policy choice, not a data fact.** Nothing in this
benchmark derives it; it is a judgement about how much analyst throughput a
review band may reasonably consume. It is set well above what the design-time
exploration found the unconstrained optimum to actually need (0% of
validation, 0% of design this run — the selected band is degenerate, see §8),
so it does not bind on this run. It exists
as a structural backstop against a *different* result on a future run, a
different generator draw, or a harder ring type — not because today's numbers
demanded it. If it needs to move, that is a decision for whoever revisits this
protocol, made explicitly, the same way `MIN_HARD_NEGATIVES_IN_RANGE` and
`MIN_POSITIVES_BELOW_MAX_NEGATIVE` are absolute rather than a margin from
whatever the incumbent currently does.

---

## 5. What was predicted, and what happened

Stated before running anything, so the record cannot be read backwards.

**Prediction (Phase 12 re-run, restated before this run):** the same
structural argument as every prior run applies again — `C_review` (500.00)
is far cheaper than `C_fn` (68,399.84), and Review waives it, so an
unconstrained sweep should prefer pulling at least some negatives into
Review rather than risking the automated-decision cost, the same way Phase
10/11 found `t_hi` meaningfully above `t_lo`.

**Result: the prediction was wrong, in a new and stronger way this time.**
`A_baseline` at the re-frozen threshold 0.18 does not merely have zero missed
positives on validation — it has **zero false positives too** (`tp` 8, `fp`
0, `fn` 0, `tn` 23 on all 31 validation components; `weight_search_protocol.md`
§8 records the same confusion matrix for the binary policy). Widening Review
downward past 0.18 still only adds review cost with nothing to rescue, as in
every prior run. But this time widening Review *upward* past 0.18 also adds
nothing: there are no false positives above the threshold left to waive
either, because there are none on validation at all. The unconstrained sweep
therefore finds the global optimum sits exactly at the binary policy —
`t_lo = t_hi = 0.18` — and every other candidate band it tried costs strictly
more, not less. **This is the most extreme case yet of the same mechanism
every run has reported**: Review can only reduce expected loss by rescuing a
missed positive or waiving a false positive, and this run's validation split
has neither for it to work with.

**This does not retire the gate.** A degenerate optimum today, on 31
validation rows with a lucky perfect split, is not proof that a different
draw, a harder ring type, or the real held-out split behaves the same way —
and indeed it does not: the held-out split has both false positives and a
missed ring (§8b). `MAX_REVIEW_RATE` stays as a structural backstop
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
  not measured, and which cannot even be exercised this run: the selected
  band routes nothing to Review at all, on either split.
- It depends on `MAX_REVIEW_RATE = 0.25`, a business choice, not a data fact —
  though it does not bind this run (the design review rate is 0%, far under
  the cap).
- It is fit to validation's specific error pattern, which this run happens to
  be a perfect one (§5). That is a property of this particular draw, not a
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

**Historical note, Phase 10/11 (superseded).** That run selected `t_lo =
0.14`, `t_hi = 0.23` against the pre-Phase-12 benchmark, pulling 5 negatives
into Review at a 17.5% validation review rate. Full tables for that run are in
git history (this section, before the Phase 12 edit). Phase 12 fixed the
`_inject_rings` RNG-isolation bug (`riskmesh/generate.py`), which moved the
scorer's frozen threshold from 0.14 to 0.18 and changed the benchmark's actual
score distribution — everything below is a fresh search against that
corrected benchmark, not a continuation of the numbers above.

Record: `out/abstention_policy.json`. `select_abstention_band()` run against
real code against the Phase 12 benchmark: 3,559 bands passed the coverage
gate out of 5,151 tried (1,592 refused), `t_lo = 0.18`, `t_hi = 0.18`, panel
PASS.

| | value |
|---|---|
| selected band | `t_lo = 0.18`, `t_hi = 0.18` (degenerate) |
| validation expected loss | **4,000.00** (binary A_baseline: 4,000.00 — identical) |
| validation review rate | **0%** (0 of 31) |
| design review rate (the gated quantity) | **0%** (0 of 69, `<= 0.25` cap) |
| validation confusion | Allow 23 (0 missed positives), Review 0, Escalate 8 (8 TP, 0 FP) |
| bands considered / refused by coverage | 3,559 / 1,592 (of 5,151 total) |

**Where the free search landed relative to the frozen binary threshold:**
`t_lo` came out exactly at 0.18 — the same number `weight_search_protocol.md`
froze for the binary policy — without being told to, the same result every
prior run reported for `t_lo` (always landing on the frozen binary threshold,
whatever that threshold currently is). §5 explains why: `A_baseline` already
has zero missed positives at 0.18, so a free search has no incentive to move
the Allow boundary. This time `t_hi` lands at exactly `t_lo` rather than above
it — every prior run's `t_hi` cleared the binary threshold by some margin to
pull in negatives worth waiving; this run has no false positives on
validation at all for `t_hi` to waive, so the search finds nothing above 0.18
worth deferring either, and the band collapses to the binary policy exactly.
This is a result, not a constraint the code enforces; a different generator
draw could move it again, and the held-out split below shows it would have
found something to do if validation itself had not been a perfect split.

**Reading this table**: it is the design-side confirmation this protocol
exists to demonstrate — a coded, gated, structurally-frozen search reproduces
what the underlying data supports — not a claim about held-out performance.

---

## 8b. The single permitted held-out read (taken, once)

Through `evaluate_frozen_abstention_policy()`, with `t_lo`/`t_hi` read back
**from** `out/abstention_policy.json` rather than recomputed. 31 test
components: 8 positive, 23 negative, 8 of the negatives carrying a family
cluster.

| | validation (selection) | **held out** |
|---|---|---|
| expected loss | 4,000.00 | **74,595.13** |
| review rate | 0% (0/31) | **0%** (0/31) |
| Allow | 23 (0 positives) | **21** (1 positive missed) |
| Review | 0 | **0** |
| Escalate | 8 (8 TP, 0 FP) | **10** (7 TP, **3 FP**) |

**Against the binary baseline on the identical test rows** (threshold 0.18,
`weight_search_protocol.md` §8's frozen result): binary expected loss
**74,595.13** with tp 7 / fp 3 / fn 1 / tn 20, against the three-way's
**74,595.13** — a delta of **0.00**, a **0%** change. The two policies are
bit-for-bit identical on every held-out row, because the frozen band is
`t_lo = t_hi`, the exact collapse condition §2 defines and `tests/test_riskmesh.py`
test_20 asserts.

**This is the weakest possible structural result, and it is reported plainly
rather than dressed up.** Review contributes nothing on held-out this run: it
does not waive any of the three false positives (all three clear `t_hi` and
are escalated, same as the binary policy would flag them), and it does not
rescue the one missed ring (which never reaches `t_lo` at all — it is an
Allow-tier miss, not a borderline case sitting in a would-be Review band).
There is no evidence in this run that an abstention band adds anything over
the binary policy; the honest conclusion is that this particular benchmark
draw, at this scorer's current weights, does not have the kind of
close-but-wrong error the review band exists to catch — every prior run's
errors were near-miss family components sitting just above the binary
threshold, and this run's held-out errors either sit well inside Escalate
(the three false positives) or are missed entirely before reaching Allow's
boundary (the one false negative).

**Tier metrics, stated so the three-way case is not read as a binary one.**
Escalate-tier precision **0.7000** (7/10) and escalate-tier FPR **0.1304**
(3/23) — identical to the binary policy's own figures, because the policies
are identical on these rows. Escalate-tier recall is **0.8750** (7 of 8
rings); the missed ring is not deferred to review (there is no review band)
— it is simply missed, `allow_missed_positives = 1`, a genuine detection
failure at this operating point rather than a near-miss the abstention
mechanism could have caught.

**The move against validation is not sample variance in the usual sense —
it is the same missed-ring mechanism `weight_search_protocol.md` §8 reports
for the binary policy**, inherited here unchanged because the band is
degenerate: one ring costs `C_fn` = 68,399.84 on its own, dwarfing the
`C_review`/`C_fp` terms that make up the rest of the table. **Neither the
validation nor the held-out figure should be quoted as "the" policy's cost**
— both are honest reads of small, different samples, and this run's gap
between them is unusually large for exactly the reason
`weight_search_protocol.md` §8 explains in full.

**D3 is resolved, not a caveat, as of Phase 10.** The original run had to
report two figures for its improvement because `C_fp` double-charged a review
at the time. `derive_costs()` now charges the review once, so there is only
ever one accounting to report — this run's finding is that the two policies
coincide exactly, not that D3 introduced any new discrepancy to reconcile.

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
* The binary-collapse test (t_lo = t_hi = 0.18 reproduces 4,000.00) removed,
  weakened, or skipped.

If any of these happens, the protocol is void and selection is re-run from a
new frozen record.
