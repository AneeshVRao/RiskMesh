# Deferred decisions

Decisions taken **knowingly**, with a measured cost, that a later phase must
revisit. This file exists so none of them gets silently inherited as "the way it
has always been". Each entry names the phase that owns the revisit.

An entry leaves this file only when the owning phase has actually made the
decision — not when someone decides it looks fine.

---

## D1 — `temporal_burst` keeps a large weight (now 0.3086) despite the redundancy question being open

**Owner: the cost-model / weight-optimisation stage. Not optional cleanup.**

**Still open after the Phase 11 re-freeze, and now with a weaker tie than
before, not a stronger one.** The original run's `E_drop_temporal` cleared all
three feasibility gates and tied `A_baseline` at *exactly* 5,348.23 validation
expected loss. Under the Phase 10/11 benchmark and the re-frozen weight vector
(`temporal_burst` now 0.3086, up from 0.2778, since `D_drop_flagged` folded
into `A_baseline` and renormalised over five signals instead of six), `E` is
**no longer even feasible** — it fails the difficulty gate outright
(`positives_below_max_negative` 0.4375 < 0.45; see `weight_search_protocol.md`
§8, second pass). So the exact three-way tie that used to be D1's strongest
evidence no longer exists as a measurement under the current weights; the
signal's redundancy is neither newly confirmed nor newly refuted by this
phase, and the question stays exactly where it was: open.

**What was measured.** The Tier 1 ablation gate
(`experiments/ablation_temporal_burst.json`) removed `temporal_burst` and
renormalised the remaining six signals to 1.0, with the ablated scorer given its
own validation-selected threshold. At the operating point the signal is exactly
redundant: held-out precision 0.6667, recall 1.0, F1 0.800 and FPR 0.1739 are
**identical** in both arms, the two scorers flag the **same 12 held-out
components**, and they disagree on only 12 of 465 ranking pairs.

**The part that makes this a deferral rather than a non-issue.** The
threshold-free diagnostic points the other way. Best achievable held-out F1 is
**0.9412 without** the signal against **0.8889 with** it — carrying
`temporal_burst` at 0.2778 costs roughly **0.05 of achievable ceiling F1**. It is
not merely useless at this weight; it is mildly harmful to the best operating
point the scorer could reach.

**Why it was left in place anyway.** Three reasons, all deliberate:

1. At the *current* threshold it costs nothing, so removing it now would be a
   change with no measurable benefit and a real risk of quietly invalidating the
   RISK-001 and RISK-003 before/after comparisons.
2. Ceiling F1 is a diagnostic computed on the held-out split. Reweighting to
   improve it would be fitting to test — precisely the thing this benchmark is
   built to rule out. A principled reweighting needs a *criterion*, and the cost
   model is what supplies one.
3. RISK-003's semantic fix is independently sound: the signal now measures what
   its name claims. Redundancy is a statement about this generator with these six
   companions, not a defect in the feature. A second ring type that bursts
   without sharing devices would plausibly change the answer.

**What the cost-model stage must actually decide.** Not "should we tidy this up",
but: given an explicit false-positive/false-negative cost, is the optimal weight
for `temporal_burst` zero, and if it is non-zero, what criterion justified it?
Whatever the answer, the reasoning goes in this file's entry before it is closed.

**Do not** read the weight (0.2778 at the time this measurement was taken,
0.3086 as of the Phase 11 re-freeze) as evidence that anyone has judged it
correct. It is carried forward on purpose, with the cost recorded here.

**Interaction with D2, found while testing it, and now realised rather than
hypothetical.** This entry originally warned that zero-weighting
`instrument_sharing` would renormalise `temporal_burst` upward (0.2778 ->
0.3247 in the isolated test). Phase 11's weight search did exactly that — it
zeroed `instrument_sharing` (D2, now closed, see below) as part of a different
policy (`D_drop_flagged`, which also zeros `merchant_concentration`), and
`temporal_burst` duly rose, to 0.3086. D1 stays open: the redundancy question
was never resolved by that move, and the current weight is once again carried
forward, not validated.

Related: `bugs.md` RISK-003, `implementation_plan.md` (Tier 1 ablation gate).

---

## D2 — RESOLVED in Phase 11 — `instrument_sharing` now carries weight 0.00

**Was: `instrument_sharing` keeps weight 0.1444 while scoring hard negatives
above positives.**

**Resolution.** Phase 10 added a real second instrument mechanism (the hybrid
pool-funded ring type, RISK-004's own suggested restart point via E6) and a
new signal, `instrument_pool_concentration`, that measures it without
`instrument_sharing`'s ring-vs-family inversion (see `bugs.md` RISK-004's
forward note). Phase 11's re-run weight search then picked `D_drop_flagged` —
which zeros `instrument_sharing` (and `merchant_concentration`, RISK-002) —
over `A_baseline` on its own merits: the two tied on validation expected loss
(8,849.98) and `D` won the tie-break on a *sharper* `positives_below_max_negative`
(0.625 vs 0.5625), not a weaker one. That winning vector was folded back into
`Config()._default_weights()` per `weight_search_protocol.md`'s "one subtlety"
rule, so `instrument_sharing` now carries weight **0.00** as the shipped
default, not as a rejected fallback.

**This is a materially different resolution from the zero-weight fallback this
entry used to describe as broken.** The original zero-weight attempt (recorded
in `bugs.md` RISK-004) *broke* the benchmark: `positives_below_max_negative`
fell to 0.1250 against the 0.20 panel bound, and the panel went PASS to FAIL.
The Phase 11 zero-weighting does the opposite: it clears both difficulty gates
with more margin than the incumbent it replaced (`positives_below_max_negative`
0.625 vs the old 0.5625; `hard_negatives_inside_positive_range` 6). The
difference is `instrument_pool_concentration` — the instrument dimension is
still represented in the scorer, just through a signal that does not have
`instrument_sharing`'s defect, so zeroing the broken one no longer removes all
instrument-axis signal the way it used to.

**The rest of this entry, kept for provenance rather than restated.** The
original owner text below described the three refuted fixes (E4, E5, E6) and
the broken zero-weight fallback, all against Tier 0's single shared-device ring
type. That record still explains *why* `instrument_sharing` itself could not be
fixed and *why* zero-weighting it used to be unsafe — it is not superseded, it
is the reason Phase 10 added a second ring mechanism instead of a fourth
`instrument_sharing` variant.

**What was measured.** On train+validation, `instrument_sharing` reads ring
0.2031 against family **0.2969** — a ring-minus-family delta of **-0.0938** at
weight **0.1444**. The signal is not merely uninformative; it pushes the hard
negatives *toward* the positive band, which is the one direction a weighted
signal must not push.

**Three fixes were pre-registered, run and refuted, and so was the fallback.**
E4 scaled ring instrument overlap with ring size and moved the delta only to
-0.0391. E5 replaced the global-cap denominator with the component's own size and
made it **worse**, at -0.2263, while saturating 78% of background components. E6
funded rings through a card pool and scored accounts-per-instrument: it inverted
the sign to +0.1576 but over-separated, single-signal F1 0.9697, and flipped the
non-triviality panel to FAIL. All records are in `experiments/`; the reasoning is
in `bugs.md` RISK-004.

**Zeroing it was tried and it breaks the benchmark.** This is no longer a
deferral for tidiness; it is a deferral because the obvious fix is measurably
wrong. Setting the weight to 0.00 and renormalising the remaining five takes
positives-below-max-negative from 0.5625 to **0.1250**, below the 0.20 bound, and
hard negatives inside the positive range from 4 to **1**. The panel verdict flips
to **FAIL**. Held-out numbers improve — precision 0.6667 -> 0.8000, F1 0.8000 ->
0.8889 — which is the tell: the detector looks better because the benchmark got
easier.

The mechanism is worth carrying forward, because it constrains *any* reweighting,
not just this one. `instrument_sharing`'s negative delta is a large part of what
holds the hard negatives up against the positives. Renormalising after removing
it also pushes weight onto `account_newness` (0.1111 -> 0.1299), which at
single-signal F1 0.9412 is the closest thing the scorer has to a lone separator.
**Any reweighting that increases `account_newness`'s share risks trivialising the
benchmark, and the non-triviality panel must be re-run and must PASS after every
weight change — not only the held-out metrics.**

RISK-001 set the precedent for zero-weighting a signal that measures the wrong
thing, but `ip_sharing` had a delta of -0.5625 with no load-bearing role in the
benchmark's difficulty. `instrument_sharing` does have one. The two cases are not
analogous, which is why the precedent does not settle it.

**What the cost-model stage must actually decide.** Not "should this be zero" —
that was tried. The real question is how to hold the benchmark's difficulty fixed
while optimising weights, given that one of the two is currently doing the other's
job. Concretely: under explicit false-positive/false-negative costs, find the
weight vector that minimises expected cost **subject to the non-triviality panel
still passing**, and report what `instrument_sharing` gets. If that constraint
turns out to be unsatisfiable, the honest conclusion is that the generator needs a
harder negative that does not depend on this signal — which is Tier 1 ring-type
work, not weight work.

**Do not** read the current 0.1444 as evidence that anyone has judged the weight
correct. Three attempts to make the signal work have failed and so has removing
it; the weight is carried forward because every alternative measured worse, not
because it is right.

Related: `bugs.md` RISK-004 and L1, `experiments/experiment_e4.json`,
`experiments/experiment_e5.json`, `experiments/experiment_e6.json`.

---

## D3 — RESOLVED in Phase 11 (fix applied in Phase 10's cost-model change)

**Was: `expected_loss()` charges an escalated false positive a review cost
twice.** `derive_costs()` used to build `C_fp` as "one manual review
(INR 500.00) plus `FP_FRICTION_RATE` (0.02) of median negative-component
exposure" — a review cost was already one of the two terms inside `C_fp` —
while `expected_loss()` computed `fn*C_fn + fp*C_fp + (tp+fp)*C_review`, which
charged a **second**, separate review cost on every flagged component,
including every false positive.

**The fix.** `derive_costs()` now builds `C_fp` as `FP_FRICTION_RATE ×`
median negative-component exposure only — friction, no embedded review term.
The generic `(tp+fp)*C_review` term is the sole place a review cost is
charged, for every flagged component regardless of correctness. This is the
first of the two equivalent options this entry used to pose ("`C_fp` drops its
own review term" vs. "the generic term excludes false positives") — the
former was chosen because it keeps the generic term's meaning ("every flag
costs a review") uniform across true and false positives, rather than special-
casing false positives out of it.

**Applied together with the Phase 10 generator change** (the hybrid
pool-funded ring type and the 8th signal), so it necessarily moved the config
fingerprint and required a full re-freeze rather than a standalone patch — see
`weight_search_protocol.md` and `abstention_protocol.md`, both re-run and
re-frozen in Phase 11. The new headline numbers, re-frozen under the fixed
formula: `A_baseline`'s validation expected loss **8,849.98**, held-out
**8,041.65** at threshold 0.14; the abstention band `t_lo=0.14, t_hi=0.23`
reduces held-out expected loss to **6,808.33**, a **15.3%** reduction against
the binary baseline on the same rows — one number now, not two under separate
accountings, because there is only one cost model to report.

**Why this could not simply be reported without a re-freeze.** Fixing the
formula moves every number that depends on it — exactly what this entry
previously said it would cost. That is why the fix accompanied Phase 10's
generator change (which was re-fingerprinting everything anyway) and Phase 11
re-ran the weight search and abstention protocols from scratch against it,
rather than patching the formula in place under the old frozen numbers.

Related: `weight_search_protocol.md` §4, §8, `abstention_protocol.md` §2, §8b,
`riskmesh/costmodel.py` (`derive_costs`, `expected_loss`),
`riskmesh/abstention.py` (`three_way_stats`).
