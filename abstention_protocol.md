# Abstention / review-band protocol — frozen before any band is selected

**Status: WRITTEN, NOT YET RUN (re-freeze pending — Tasks 3–5 benchmark).**
Tasks 3–5 rebuilt the benchmark (five ring types, four hard-negative cluster
types, 19,310 transactions) and moved the config fingerprint from
`c3ee14627c2c2ce2` toward whatever `weight_search_protocol.md`'s own re-freeze
settles on as the incumbent (that protocol's fold-back rule may change
`Config()._default_weights()`, which is itself part of the fingerprint). Every
number this protocol had frozen — band `t_lo = 0.18`, `t_hi = 0.18`, held-out
expected loss 74,595.13 — describes a run against the old benchmark and no
longer reproduces, so §8/§8b have been cleared back to a pending placeholder
and this document is committed in that state, **before**
`select_abstention_band()` runs against the new benchmark. §8/§8b are
appended only after `experiments/abstention_policy.json` exists (which itself
requires `experiments/weight_policy.json` to already be frozen — this band is
layered on the already-selected `A_baseline` scorer and its binary threshold)
and the single held-out read has been taken through
`evaluate_frozen_abstention_policy()`.

**The mechanism (§2), the one new assumption (§3), and the gate (§4) are
unchanged from every prior run.** Only the generator producing the rows the
band is scored against — and possibly the frozen binary threshold it is
layered on — has changed.

Re-run previously because Phase 12 fixed a real RNG-isolation bug in
`_inject_rings` (`riskmesh/generate.py`'s module comment; the
instrument-mechanism branch let the main stream's consumption depend on
`is_hybrid`, a data-dependent branch) which changed actual generator output
without moving the config fingerprint. (Phase 10/11 had already re-run this
protocol once before, for an unrelated reason — the scorer and its threshold
moving from Phase 10's generator and D3 cost-model changes.) Superseded §8/§8b
tables for both prior runs are in git history at this section's earlier
revisions, not reproduced here.

This layers a second decision policy on top of the already-frozen A_baseline
scorer and its already-frozen binary threshold — whatever
`weight_search_protocol.md` §8 currently reports for the re-frozen benchmark,
read from `experiments/weight_policy.json` rather than quoted here, since that
protocol's own re-freeze (and possible fold-back iteration) determines it
before this document's freeze stage runs. Neither the scorer's eight weights
nor the binary threshold's own reported numbers are reopened, touched, or
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
   for all three tiers on test. No second read. **Not yet taken — see §8b.**

---

## 8. Outcome — PENDING

## 8b. The single permitted held-out read — PENDING

Neither §8 nor §8b has been run. Both are populated, in full, only after
`python -m riskmesh.freeze abstention` has produced
`experiments/abstention_policy.json` against the Tasks 3-5 benchmark (layered
on whatever `experiments/weight_policy.json` currently freezes as the
A_baseline scorer and its binary threshold) and the single held-out read has
been taken through `evaluate_frozen_abstention_policy()`. The prior run's
finding (degenerate band `t_lo = t_hi = 0.18`, bit-for-bit identical to the
binary policy on every held-out row, held-out expected loss 74,595.13) is
superseded and lives in git history at this section's prior revision, not
reproduced here.

## 9. What would invalidate this protocol

Stated so it is falsifiable, mirroring `weight_search_protocol.md` §7:

* `t_lo` or `t_hi` chosen, adjusted, or re-swept after a held-out number is
  seen.
* `MAX_REVIEW_RATE` changed after seeing what band it would admit or refuse.
* The perfect-analyst-review assumption in §3 replaced with a measured rate
  derived from anything other than an explicit, separately-declared model.
* Any expected-loss number produced for a band that fails either gate.
* More than one held-out read.
* The binary-collapse test (`t_lo = t_hi` reproduces the binary policy's
  expected loss exactly, `tests/test_riskmesh.py`) removed, weakened, or
  skipped.

If any of these happens, the protocol is void and selection is re-run from a
new frozen record.
