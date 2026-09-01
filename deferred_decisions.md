# Deferred decisions

Decisions taken **knowingly**, with a measured cost, that a later phase must
revisit. This file exists so none of them gets silently inherited as "the way it
has always been". Each entry names the phase that owns the revisit.

An entry leaves this file only when the owning phase has actually made the
decision — not when someone decides it looks fine.

---

## D1 — RESOLVED by Task 6's re-freeze — `temporal_burst` now carries weight 0.00

**Was: `temporal_burst` keeps a large weight (0.2778, later 0.3086) despite the
redundancy question being open.**

**Resolution.** This entry's own text (below) named the one thing that would
"plausibly change the answer": *"A second ring type that bursts without
sharing devices."* Tasks 3-4 added exactly that — four new ring types
(`ip`, `instrument`, `refund`, `hybrid`) that burst through the identical
code path as the original `device` type (`_inject_rings`'s unconditional
`bursts = rng.random() >= cfg.p_ring_no_burst` draw, applied to every ring
regardless of type) — plus three new hard-negative cluster types alongside
family. Task 6's re-run `weight_search_protocol.md` search then answered the
open question with a real result, not a tie: `E_drop_temporal` (which zeros
`temporal_burst`) beat the prior incumbent `A_baseline` **outright** on
validation expected loss (43,331.85 vs 57,601.30 — not a tie, a win), cleared
both difficulty gates with room to spare (pbmn 0.6458 against the 0.45 floor,
52 hard negatives against the floor of 4), and held the winning position
across the full `FN_ABSORBED_FRACTION x FP_FRICTION_RATE` sensitivity grid.
Per the protocol's own fold-back rule, `E_drop_temporal`'s vector became the
new `Config()._default_weights()` incumbent, and a second pass against it
reached a fixed point in one further iteration (`A_baseline`,
`D_drop_flagged`, and `E_drop_temporal` now all describe the identical
vector). `temporal_burst` is weight **0.0000** in the shipped scorer.

**The mechanism is not the one this entry's hedge anticipated, and that is
worth stating plainly rather than glossing over.** The hedge speculated a
second bursting-without-device-sharing ring type would make `temporal_burst`
*more* valuable, by giving it something to detect that `device_sharing`
could not. What was actually measured (`riskmesh/config.py`'s
`_default_weights()` docstring, `riskmesh/score.py`'s `_burst()` docstring):
`temporal_burst` separates rings from each of the four hard-negative cluster
types individually well (single-signal F1 0.71 against family, up to 0.91
against office/hostel) but only weakly against all four combined — a genuine
mixture effect no single weight can resolve, because the four hard-negative
types differ in how and whether they collide with it. More ring diversity
made the signal *harder* to weight usefully, not easier. This is a complete,
evidence-backed answer to the question this entry's owner ("the cost-model /
weight-optimisation stage") was asked to decide: under an explicit cost
model with the panel and difficulty gates enforced, the optimal weight for
`temporal_burst` is zero, and the criterion that justified it is the same
expected-loss objective and feasibility gates every other candidate was held
to — no ad hoc rule, no relaxed bound.

**Superseded background, kept for provenance rather than restated.** The
paragraphs below described the state of this question through the Phase 11
re-freeze, when `E_drop_temporal` had gone from tying the incumbent to
failing the difficulty gate outright — the opposite trajectory from Task 6's
result. That history is why this was the longest-open entry in this file,
and it is left as the record of why the answer was not obvious in advance.

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

**[Answered by Task 6 — see the Resolution at the top of this entry.]** The
optimal weight is zero, under the identical expected-loss criterion and
feasibility gates this paragraph called for, measured against the harder
benchmark Task 3-4 built. The paragraph above is kept as the exact question
that was eventually answered, not as a still-open ask.

**Historical note, no longer current advice.** This paragraph used to read
"do not read the weight as evidence that anyone has judged it correct" —
true of the 0.2778/0.3086 weights it referred to at the time, false of the
current weight (0.0000), which the cost model above did explicitly judge.
Kept for the record of what this entry withheld judgement on before Task 6.

**Interaction with D2, found while testing it, and now realised rather than
hypothetical.** This entry originally warned that zero-weighting
`instrument_sharing` would renormalise `temporal_burst` upward (0.2778 ->
0.3247 in the isolated test). Phase 11's weight search did exactly that — it
zeroed `instrument_sharing` (D2, now closed, see below) as part of a different
policy (`D_drop_flagged`, which also zeros `merchant_concentration`), and
`temporal_burst` duly rose, to 0.3086. At the time this paragraph was written,
D1 stayed open: the redundancy question was never resolved by that move, and
the weight was once again carried forward, not validated. Task 6's re-freeze,
recorded in the Resolution at the top of this entry, is what finally answered
it — by a different mechanism (a mixture effect across four hard-negative
types) than the one D2's interaction with D1 predicted.

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

**This paragraph is historical.** `instrument_sharing` no longer carries
0.1444 — as the Resolution at the top of this entry already states, it has
carried weight **0.00** since Phase 11's `D_drop_flagged` fold-back, and
Task 6's re-freeze against the current five-ring-type benchmark reproduces
`A_baseline`/`D_drop_flagged` tying at that same zero weight
(`experiments/weight_policy.json`). Do not read the 0.00 either as evidence
of a settled judgement on the *feature* — as the Resolution explains, it is
zero now because `instrument_pool_concentration` carries the instrument-axis
signal instead, not because `instrument_sharing`'s own defect was fixed.

Related: `bugs.md` RISK-004 and L1, `experiments/experiment_e4.json`,
`experiments/experiment_e5.json`, `experiments/experiment_e6.json`; `bugs.md`
RISK-005 (the identical mis-signed-against-a-specific-hard-negative-type
pattern, found on `device_sharing` against family and office clusters, masked
by the same kind of aggregate-negatives check that hid this signal's own
RISK-004-era problem).

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
re-frozen in Phase 11, then again in Phase 12 after an RNG-isolation bug fix
in `_inject_rings` changed the generator's actual output without moving the
fingerprint (see `riskmesh/generate.py`'s module comment and
`weight_search_protocol.md`'s Status header). The current headline numbers,
re-frozen under the fixed formula and the corrected generator:
`A_baseline`'s validation expected loss **4,000.00**, held-out **74,595.13**
at threshold 0.18 (one missed ring dominates this figure — see
`weight_search_protocol.md` §8); the abstention search this run selects the
degenerate band `t_lo=0.18, t_hi=0.18`, identical to the binary policy on
these rows, a **0%** change rather than a reduction (see
`abstention_protocol.md` §8b) — there is only one cost model to report either
way, which is the property D3 fixed and remains true regardless of which
run's numbers are quoted.

**Why this could not simply be reported without a re-freeze.** Fixing the
formula moves every number that depends on it — exactly what this entry
previously said it would cost. That is why the fix accompanied Phase 10's
generator change (which was re-fingerprinting everything anyway) and Phase 11
re-ran the weight search and abstention protocols from scratch against it,
rather than patching the formula in place under the old frozen numbers.

Related: `weight_search_protocol.md` §4, §8, `abstention_protocol.md` §2, §8b,
`riskmesh/costmodel.py` (`derive_costs`, `expected_loss`),
`riskmesh/abstention.py` (`three_way_stats`).

---

## D4 — OPEN — the shipped operating threshold is F1-selected, not loss-selected, contrary to a PRD Must-have

**Owner: whichever phase next revisits `out/threshold.json`. Not optional
cleanup — this is a Must-have compliance gap, found during Task 8's
documentation sweep, that the original audit missed.**

**What was decided.** `PRD.md`'s "Threshold optimization" row is a
**Must-have**: *"Selects an operating threshold based on expected financial
loss rather than maximizing a single ML metric,"* with the acceptance
criterion *"selected threshold minimizes expected validation loss under
documented cost assumptions; held-out test results then reported"* and the
PRD's own worked example (line 641) stating plainly: *"We do not choose the
threshold that maximizes F1. We choose the operating point that minimizes
expected financial loss under explicit cost assumptions."*

`out/threshold.json` — the threshold the pipeline actually ships and the
`/metrics`, `/rings`, and `/threshold-analysis` endpoints actually serve — is
produced by `select_threshold()`, which selects **the threshold that
maximises F1** on validation (`selection_metric: "f1"` is printed directly in
the file). It is not loss-selected. This is exactly the thing the PRD's own
sentence says not to do.

**This is not a mislabelled duplicate of the D1-style redundancy questions
above — a genuinely loss-selected threshold already exists and is frozen.**
`select_weights()`'s own expected-loss search, run as part of the weight
search protocol, does select a threshold by minimising expected validation
loss, and its result is frozen in `experiments/weight_policy.json`'s
`held_out` block: threshold 0.10, held-out F1 0.5432, expected loss 92,263.55.
The gap is not "no loss-selected threshold was ever computed" — it is that
**the pipeline's headline number, and everything the console displays, comes
from the other selection procedure.** Two real, frozen, correctly-computed
thresholds exist on this benchmark, and the PRD names one of them as
mandatory while the pipeline ships the other.

**What was measured, so the cost of each choice is explicit, not asserted.**

| | `out/threshold.json` (shipped) | `weight_policy.json` `held_out` (PRD-compliant) |
|---|---|---|
| threshold | 0.22 | 0.10 |
| selected by | maximise F1 on validation | minimise expected loss on validation |
| held-out F1 | 0.7500 | 0.5432 |
| held-out expected loss | not the objective this threshold was chosen for | **92,263.55** |
| held-out FPR | 0.0787 | 0.4045 |
| ring recovery | 13/20 | 16/20 |

Switching the shipped threshold to the loss-selected one would roughly
**halve F1** (0.75 -> 0.54) and **more than quintuple FPR** (0.0787 -> 0.4045)
while catching three more rings (13 -> 16 of 20) — a materially different,
much higher-review-volume operating point (51.8% review rate against the
current threshold's much lower flag rate), not a cosmetic change.

**Why this was not fixed here.** Switching `out/threshold.json`'s selection
metric would move every headline number this documentation sweep just wrote
down a second time (README's "Current figures", `PRODUCT.md`, the API's
served metrics, every test asserting the current 0.22/0.75 figures) and is
scoped modelling/product work — deciding whether the console should serve
the loss-selected point, some other explicit cost-based point, or keep F1 as
a documented, disclosed departure from the PRD — not a side effect of a
documentation-only task. This entry exists so the gap is on record rather
than quietly inherited as "the way it has always been," per this file's own
opening sentence.

**What the owning phase must actually decide.** Not "which threshold is
better" — both are real and defensible for different purposes. The decision
is whether `out/threshold.json` should be produced by an expected-loss
selection (to satisfy the PRD Must-have literally, at the cost of the
console's current low-FPR operating point) or whether the F1-selected
threshold stays the shipped default with the PRD gap disclosed permanently
(the position this documentation sweep takes, pending that decision).
Whatever the answer, the reasoning goes in this entry before it is closed.

**Do not** read the fact that `out/threshold.json` is F1-selected as evidence
that anyone has judged it PRD-compliant. It is carried forward because
Task 8's brief instructed "document this gap openly ... do NOT change the
selection metric," not because the gap has been resolved.

Related: `PRD.md` "Threshold optimization" (Must-have row), line 343 ("False-
Positive Cost Model"), line 641 (worked example), line 686 (Assumption 3);
README "Two Tier 1 operating points"; `riskmesh/evaluate.py`
(`select_threshold`); `riskmesh/costmodel.py` (`select_weights`).

---

## D5 — OPEN — no weight-search candidate re-enables `ip_sharing`, and it is now the scorer's one clear recall gap

**Owner: the next weight-search re-freeze. Not optional cleanup.**

**What was decided.** `ip_sharing` has carried weight 0.00 since Tier 0
(RISK-001) — correctly, at the time, since no `ip`-type ring existed and the
signal measured nothing but back-door household detection. Task 3 then added
a real shared-IP ring type. `weight_search_protocol.md`'s five candidates
(`A_baseline`, `B_equal`, `C_separation_proportional`, `D_drop_flagged`,
`E_drop_temporal`) were declared before Task 3 existed and none of them
re-introduces `ip_sharing`: `A`/`D`/`E` all zero it identically to the
pre-Task-3 vector, `B_equal` and `C_separation_proportional` are both refused
by the difficulty gate before their weight on this signal matters. The
candidate set simply predates the ring type it would need to react to.

**What this costs, measured, not estimated.** Per-ring-type recall on the
current held-out test split (23 positive components — verified directly by
scoring `test` under `ring_score`'s frozen threshold 0.22 and grouping by
`ring_type`, not read off a single aggregate number):

| ring type | n | `ring_score` recall | `transaction_level` recall |
|---|---|---|---|
| device | 4 | 4/4 | 2/4 |
| hybrid | 4 | 4/4 | 4/4 |
| instrument | 7 | 5/7 | 5/7 |
| **ip** | 4 | **1/4** | 2/4 |
| refund | 4 | 4/4 | 4/4 |
| **total** | 23 | **18/23** | 17/23 |

`ip`-type rings are the scorer's one clear weak spot: 1 of 4 caught, the
worst recall of any ring type and the only one where the naive
`transaction_level` baseline (which has no shared-IP concept at all) does
*better*. The mechanism is exactly what the weight vector predicts — the one
signal built to detect shared-IP convergence contributes nothing to the
score for any component, `ip`-type ring or not.

**Why this was not fixed here.** Re-declaring the weight-search candidate
set (adding a sixth candidate that restores `ip_sharing`, or re-deriving the
existing five's ratios to include it) is a new selection protocol run,
subject to Global Constraint G4 (frozen before any candidate is scored) —
exactly the kind of re-freeze this documentation sweep is not authorised to
trigger. Doing it here would also move every headline number this sweep just
wrote down a second time.

**What the owning phase must actually decide.** Whether a new weight-search
candidate that restores non-zero weight to `ip_sharing` clears the panel and
difficulty gates on the current five-ring-type benchmark, and if so, whether
it beats the current incumbent on expected loss — the same question every
prior candidate was held to, no relaxed bar for this one. If no such
candidate is feasible, the honest conclusion is a generator-side one:
`ip_sharing`'s current definition may need a different design before a
linear weight can use it without over- or under-separating, the same shape
of finding `deferred_decisions.md` D2 reached for `instrument_sharing`.

**Do not** read `ip_sharing`'s weight of 0.00 as evidence that the shared-IP
ring type has been evaluated and found not worth detecting. It is carried
forward because no candidate that could re-enable it has ever been run
against a benchmark where doing so would matter.

Related: `bugs.md` RISK-001 (why the weight was originally zeroed, before any
IP ring type existed); README "Read this before the numbers" finding 1 and
"Baselines" (the F1/FPR comparison this recall gap explains); `weight_search_protocol.md`
§2 (candidate declarations); `riskmesh/config.py` (`ring_type_ip`,
`ring_shared_ip_share`).
