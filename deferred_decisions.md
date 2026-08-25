# Deferred decisions

Decisions taken **knowingly**, with a measured cost, that a later phase must
revisit. This file exists so none of them gets silently inherited as "the way it
has always been". Each entry names the phase that owns the revisit.

An entry leaves this file only when the owning phase has actually made the
decision — not when someone decides it looks fine.

---

## D1 — `temporal_burst` keeps weight 0.2778 despite being redundant

**Owner: the cost-model / weight-optimisation stage. Not optional cleanup.**

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

Related: `bugs.md` RISK-003, `implementation_plan.md` (Tier 1 ablation gate).

---

## D2 — `instrument_sharing` keeps weight 0.1444 while scoring hard negatives above positives

**Owner: the cost-model / weight-optimisation stage. Not optional cleanup.**

**What was measured.** On train+validation, `instrument_sharing` reads ring
0.2031 against family **0.2969** — a ring-minus-family delta of **-0.0938** at
weight **0.1444**. The signal is not merely uninformative; it pushes the hard
negatives *toward* the positive band, which is the one direction a weighted
signal must not push.

**Two fixes were pre-registered, run and refuted.** E4 scaled ring instrument
overlap with ring size and moved the delta only to -0.0391. E5 replaced the
global-cap denominator with the component's own size and made it **worse**, at
-0.2263, while introducing a size-2 saturation artefact that sent background to
0.5901. Both records are in `experiments/`; the reasoning is in `bugs.md`
RISK-004.

**Why the weight was left alone anyway.** Changing it is a weight decision, and
this project has one rule about those: they need a criterion, and the criterion
comes from the cost model. Zeroing it now would be the same judgement call made
without the thing that justifies it. RISK-001 set the precedent — `ip_sharing`
was zero-weighted at -0.5625 — but that was done as part of a scoped fix with a
before/after comparison, not as a loose adjustment.

**What the cost-model stage must actually decide.** Given explicit
false-positive/false-negative costs: is the optimal weight for
`instrument_sharing` zero? If the injector-side fix (RISK-004 option 2) lands
first and the delta turns positive, this entry closes on its own — but it must
close *explicitly*, with the number that justified it recorded here.

**Do not** read the current 0.1444 as evidence that anyone has judged the weight
correct. Two attempts to make the signal work have failed, and the weight is
carried forward pending a criterion.

Related: `bugs.md` RISK-004, `experiments/experiment_e4.json`,
`experiments/experiment_e5.json`.
