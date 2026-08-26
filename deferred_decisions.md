# Deferred decisions

Decisions taken **knowingly**, with a measured cost, that a later phase must
revisit. This file exists so none of them gets silently inherited as "the way it
has always been". Each entry names the phase that owns the revisit.

An entry leaves this file only when the owning phase has actually made the
decision — not when someone decides it looks fine.

---

## D1 — `temporal_burst` keeps weight 0.2778 despite being redundant

**Owner: the cost-model / weight-optimisation stage. Not optional cleanup.**

**Still open after weight selection, and now with a third measurement behind
it.** Policy E (`temporal_burst` zeroed, the other five renormalised) cleared all
three feasibility gates and tied A_baseline at *exactly* 5,348.23 validation
expected loss, differing only in the threshold that reaches it — 0.26 against
0.23. So removing the signal changes no held-out metric (the ablation), and no
expected-loss figure either. A was retained on the incumbent tie-break, which
means **the weight survived because nothing beat it, not because it was
validated.** That is the same status as before, held more firmly.

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

**Do not** read the current 0.2778 as evidence that anyone has judged the weight
correct. It is the pre-ablation weight, carried forward on purpose, with the cost
recorded here.

**Interaction with D2, found while testing it.** Zero-weighting
`instrument_sharing` renormalises `temporal_burst` from 0.2778 up to **0.3247** —
so the two entries are coupled. Any fix for D2 that removes weight from a signal
increases the share held by one this file already records as redundant and mildly
harmful. Decide D1 and D2 together, not in sequence.

Related: `bugs.md` RISK-003, `implementation_plan.md` (Tier 1 ablation gate).

---

## D2 — `instrument_sharing` keeps weight 0.1444 while scoring hard negatives above positives

**Owner: the cost-model / weight-optimisation stage. Not optional cleanup.**

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

## D3 — `expected_loss()` charges an escalated false positive a review cost twice

**Owner: the cost-model / weight-optimisation stage. Same owner as D1 and D2,
not a new one.**

**What was found, and when.** Surfaced while designing the abstention/review-
band layer (`abstention_protocol.md`), not while touching the frozen binary
cost model itself. `derive_costs()` builds `C_fp` as "one manual review
(INR 500.00) plus `FP_FRICTION_RATE` (0.02) of median negative-component
exposure" — i.e. a review cost is already one of the two terms inside `C_fp`.
`expected_loss()` then computes `fn*C_fn + fp*C_fp + (tp+fp)*C_review`, which
charges a **second**, separate review cost on every flagged component,
including every false positive. So an escalated false positive is charged a
review cost through two different line items: once inside `C_fp`'s own
derivation, and once again through the generic `(tp+fp)*C_review` term that
prices analyst effort on every flag regardless of correctness.

**Why it has not been touched.** Fixing either the `C_fp` derivation or the
`expected_loss()` formula changes the value of every already-frozen number that
depends on it — `A_baseline`'s validation expected loss 5,348.23, its held-out
expected loss 9,392.92, the entire `weight_search_protocol.md` §8 table, and the
flag-everything comparisons computed against them. None of those are wrong on
their own terms — they are internally consistent with the formula as written —
but silently changing the formula after freezing them would move numbers this
project has repeatedly said must not move without a new frozen record. The
abstention-band cost formula in `abstention.py` **carries the same convention
forward unchanged** (an Escalate-negative costs `C_fp + C_review`, matching
`expected_loss()` exactly) for the same reason: consistency with the frozen
baseline it is being compared against matters more here than correcting a
double-count that does not change which policy wins under either accounting
(the ranking is driven by `C_fn`'s size relative to everything else, not by
this).

**What the cost-model stage must actually decide, next time it is revisited.**
Whether `C_fp`'s derivation should drop its own "one review" term (since the
generic per-flag review cost already prices that effort), or whether the
generic `(tp+fp)*C_review` term should exclude false positives specifically
(since their review cost is priced inside `C_fp` instead) — the two are
equivalent in effect, and the choice is about which term should own the
concept, not about the size of the correction, which is small either way (500
of the total 848.23 assigned to a false positive under the current formula).
Whichever is chosen, every downstream number that used `expected_loss()` under
the old convention needs its own new frozen record, exactly as changing a
weight or a threshold would.

**Do not** read the current formula as evidence anyone has judged the
double-charge acceptable. It is carried forward because fixing it silently
would move the 5,348.23 / 9,392.92 baseline without a new freeze, not because
it is correct.

**Measured consequence, added after the abstention held-out read — this is why
D3 is no longer only a tidiness item.** The abstention band's headline result
is that it converts four escalated false positives into four reviews, and the
size of that improvement depends directly on this double-charge. Under the
current formula the held-out comparison is 9,392.92 (binary) against 6,000.00
(three-way), a **36.1%** reduction. Under a D3-corrected `C_fp` — friction only,
348.23, with the generic per-flag review cost left to price the analyst effort
once — the same comparison is 7,392.92 against an unchanged 6,000.00, an
**18.8%** reduction. The direction, the sign, and the structural finding (zero
escalated false positives on the held-out split) are robust under either
accounting; only the magnitude moves, and it roughly halves.

So D3 now has a concrete downstream effect on a reported number, not just an
internal inconsistency: **any claim about how much the abstention band saves is
sensitive to it**, and both figures must be quoted together until it is
resolved. This does not change the decision to carry the convention forward —
that still rests on not silently moving a frozen baseline — but it raises the
priority of resolving it before the cost model is quoted in a pitch, and it
means the eventual fix must re-freeze the abstention record as well as the
weight-search one. Recorded in `experiments/abstention_policy.json` under
`held_out.d3_sensitivity`.

Related: `weight_search_protocol.md` §4, `abstention_protocol.md` §2 and §8b,
`riskmesh/costmodel.py` (`derive_costs`, `expected_loss`),
`riskmesh/abstention.py` (`three_way_stats`).
