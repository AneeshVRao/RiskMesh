# RiskMesh — bug log

One entry per bug, newest at the top. Fill in **every** field before touching
code — the point of this file is to reason about a fix rather than guess at one.
Delete an entry once its fix is verified by the matching `testing.md` row.

Open bugs: 1 open (RISK-005). 5 closed/resolved (RISK-001, RISK-002,
RISK-003, RISK-004, B1). RISK-002 moved from "OPEN, deferred" to "RESOLVED BY
WEIGHT" during Task 8's documentation sweep, once its weight was confirmed at
0.00 since Phase 11 — see its entry below; the underlying feature-level
mis-sign was never fixed and the entry says so. RISK-005 is new: found during
the same sweep, `device_sharing` (the scorer's largest weight, 0.3929) is
mis-signed against `family` and `office` hard negatives specifically, masked
by the panel's pooled-negatives sign check — the same class of blind spot
RISK-001 and RISK-004 were, now on the top-weighted signal.
Standing lessons: L1 (size-based normalisation), L2 (held-out F1 as an objective).

Knowingly-deferred *decisions* (as opposed to bugs) live in
`deferred_decisions.md`. D1 there recorded that `temporal_burst` was carried
at a large weight despite an open redundancy question; Task 6's re-freeze
answered it (weight now 0.0000) and D1 is closed. D4 and D5 are new,
currently open entries: D4 is the shipped `out/threshold.json` being
F1-selected rather than loss-selected, contrary to a PRD Must-have; D5 is
that no weight-search candidate re-enables `ip_sharing` now that a real
shared-IP ring type exists, leaving it the scorer's weakest ring-type recall.

---

## Entry template

### [ID] Short title

- **Symptom:** what actually happens, observably. Not the suspected cause.
- **Expected:** what should happen instead, and which `testing.md` row says so.
- **Error:** exact traceback or assertion output, pasted verbatim.
- **Files involved:** the files in the actual code path, not everything nearby.
- **Reproduce:** the exact command, plus the seed if it is seed-dependent.
- **Suspected cause:** the hypothesis, stated so it can be proven wrong.
- **Fix:** what changed, and which check now covers it.

---

<!-- Add entries below this line. -->

### RISK-005 — device_sharing, the scorer's largest weight, is mis-signed against two of four hard-negative types

- **Status: OPEN.** Found during Task 8's documentation sweep, confirmed and
  extended by the coordinator's own investigation before this entry was
  written. Not fixed here — `riskmesh/integrity.py`'s `signal_sign_check`
  panel check is left exactly as it is; this is a named, deferred gap, not a
  silent code change. Reported as FLAG-level risk in kind, though the panel's
  aggregate check does not currently surface it at all (see below).
- **Symptom:** on normalised values (train+validation, current benchmark,
  computed per hard-negative cluster type from `out/components.csv` — not
  from the panel's own pooled-negatives view, which cannot see this):

  | cluster type | n | ring = 0.1837 vs type = | delta |
  |---|---|---|---|
  | family | 40 | 0.3523 | **-0.1686** (badly mis-signed) |
  | office | 10 | 0.2636 | **-0.0799** (mis-signed) |
  | hostel | 10 | 0.0000 | +0.1837 (fine) |
  | retail | 24 | 0.0000 | +0.1837 (fine) |

  `device_sharing` carries weight **0.3929** — the single largest weight in
  the entire 8-signal vector — and it actively favours `family` and `office`
  clusters over rings. Both cluster types converge on shared devices by
  design: `config.py`'s own family-cluster documentation states households
  run up to 8 accounts on one device specifically to keep "the device-only
  baseline honest," and `office` clusters share a device pool by the same
  logic (workplace convergence). The signal is doing exactly what those two
  hard-negative types were built to test it against, and losing.
- **Expected:** a weighted signal should be higher on positives than on the
  specific hard negatives it is meant to be hard against, not merely higher
  than the *average* of all four hard-negative types combined.
- **Error:** no exception. `non_triviality.signal_sign_check` in
  `out/integrity_report.json` reads `device_sharing` as correctly signed
  (ring-vs-all-negatives delta +0.0468, `weighted_contribution` +0.0184,
  status "ok") because it pools all 176 train+validation negatives together
  — 40 family + 10 office (mis-signed, 50 components) are diluted against 10
  hostel + 24 retail + 92 background (correctly signed, 126 components). The
  aggregate check cannot see a signal that is right on balance but wrong
  against two specific, structurally-designed hard negatives.
- **Files involved:** `riskmesh/score.py` (signal definition, unchanged —
  the feature computes exactly what it claims to), `riskmesh/config.py`
  (weight 0.3929, `_default_weights()`), `riskmesh/integrity.py`
  (`signal_sign_check`, the masking mechanism — **not modified**, see Status).
- **Reproduce:** `python -m riskmesh`, seed 20260824; group
  `out/components.csv`'s train+validation rows by `cluster_type` and compare
  each type's `device_sharing_norm` mean against the ring population's.
- **Suspected cause:** structurally identical to RISK-001 (`ip_sharing`,
  masked by pooling against a majority-background negative set before any
  IP-sharing hard negative existed) and RISK-004 (`instrument_sharing`,
  masked the same way before a second instrument mechanism existed). Here,
  the mask is `signal_sign_check`'s own pooling of four structurally
  different hard-negative types into one "all negatives" mean — a design
  that was adequate when only one hard-negative type (family) existed and
  became a blind spot the moment Task 4 added three more with different
  device-sharing behaviour. This is not a new class of defect; it is the
  same class discovered a third time, on the highest-weighted signal, only
  because a benchmark with four distinct cluster types now exists to reveal
  it.
- **Fix:** deferred, deliberately. Two directions were considered (per the
  coordinator's review) and neither is implemented here: (1) re-run the
  weight search with a candidate that reduces or re-derives
  `device_sharing`'s weight in light of this finding, or (2) change
  `signal_sign_check` itself to report per-hard-negative-type deltas instead
  of (or alongside) the pooled figure, which would have caught this and
  RISK-001/RISK-004 in the same pass they were actually found. **Neither was
  done in this documentation sweep** — (1) is a new selection protocol run
  (Global Constraint G4: frozen before any candidate is scored, not
  something a documentation task may trigger), and (2) is a code change to
  `riskmesh/integrity.py`, explicitly out of scope and explicitly not
  authorised by the coordinator's ruling, so that the panel's blind spot
  stays visible and named rather than quietly patched.
- **What the cost-model / weight-optimisation stage must actually decide.**
  Not "should `device_sharing` be zero-weighted" — RISK-001 and RISK-004 both
  show that blindly zeroing a signal with a real structural role can break
  the benchmark's own difficulty gates. The real question, in the same shape
  D2 and D5 pose: given an explicit cost, is 0.3929 still the right weight
  for a signal that is mis-signed against 50 of 176 train+validation
  negatives, and if the panel's aggregate check should be widened to a
  per-cluster-type view to catch this class of defect going forward, that is
  its own scoped change to `riskmesh/integrity.py` — not bundled into a
  weight re-run.
- **Do not** read `device_sharing`'s weight of 0.3929 as evidence that
  anyone has judged it correct against `family` and `office` specifically.
  It is the incumbent's current weight, carried forward because no
  per-cluster-type-aware selection has ever been run against it.

Related: `deferred_decisions.md` D2 (the identical pattern on
`instrument_sharing`, cross-referenced from there); RISK-001, RISK-004 (the
same masking mechanism, found twice before); README "The scorer" (the
ring-vs-family finding this entry formalises); `out/integrity_report.json`
-> `non_triviality.signal_sign_check`.

### L2 — held-out F1 is not a safe objective for weight selection on this benchmark

**A standing lesson, filed separately from RISK-004 because it is not about
instruments.** It is the single most important thing this build has learned about
how to choose weights, and it must be in front of whoever runs the cost model.

**The observation.** Held-out F1 improved from 0.8000 to **0.8889** twice, by two
mechanisms with nothing in common, and **both times the non-triviality panel went
from PASS to FAIL**:

| | held-out F1 | held-out precision | FPR | positives below max negative | panel |
|---|---|---|---|---|---|
| current scorer | 0.8000 | 0.6667 | 0.1739 | 0.5625 | **PASS** |
| E6 funding-pool signal | 0.8889 | 0.8000 | 0.0870 | 0.0625 | **FAIL** |
| zero-weight fallback | 0.8889 | 0.8000 | 0.0870 | 0.1250 | **FAIL** |

E6 improved F1 by giving the scorer a near-separator (`instrument_sharing`
single-signal F1 0.9697, family exactly 0.0000). The zero-weight fallback
improved F1 by renormalising weight onto `account_newness`, whose single-signal
F1 is 0.9412. Different signals, different mechanisms, identical held-out
numbers, identical failure.

**Why it happens.** Held-out F1 measures the *pair* (model, benchmark). It goes
up when the model gets better and it goes up when the benchmark gets easier, and
it does not distinguish the two. On this dataset the hard negatives are held in
the positive score range by a handful of signals; anything that removes their
influence -- a new dominant signal, or reweighting away from the ones doing that
work -- raises F1 by making the task easier. **An optimiser pointed at held-out
F1, or at expected loss without a difficulty constraint, will find these
solutions preferentially, because they are the cheapest way to improve the
number.**

**What to do instead.** Treat the non-triviality panel as a **feasibility
constraint, not a report**. A weight vector that fails the panel is not a
worse candidate -- it is not a candidate. Concretely:

1. The panel must be re-run on train+validation after **every** weight change,
   before any performance metric is read.
2. A candidate that fails the panel must be structurally unable to receive a
   score, in the same way `held_out_view()` is structurally unable to return test
   rows without a frozen record. Enforced in `riskmesh/costmodel.py` by
   `gated_expected_loss()`, which raises `PanelGateFailure` rather than returning
   a number. See `weight_search_protocol.md`.
3. Report `positives_below_max_negative` and
   `hard_negatives_inside_positive_range` alongside every F1 figure in any
   comparison table, so a reader can see the difficulty as well as the score.

**The generalisation.** Any benchmark whose difficulty is partly produced by the
model's own components has this failure mode. Optimising a metric computed on
that benchmark will silently trade difficulty for score unless difficulty is
constrained separately. Related: `deferred_decisions.md` D1 and D2.



### L1 — size-based normalisation degenerates at small component sizes

**A standing lesson, not a bug.** Filed separately from RISK-004 on purpose: the
ring-vs-family direction failure is specific to that comparison, this is not.
It applies to any feature, in any tier, whose denominator is the size of the
thing being scored.

**What happened.** E5 redefined `instrument_sharing` as
`max_accounts_on_one_instrument / component_size`. For a component of size 2
whose two accounts touch one instrument, that is `2/2 = 1.0` — the maximum score,
from the smallest and least interesting structure in the graph. Design-split
components are dominated by exactly that shape: **31 of 69 are size 2 and 41 of
69 are size 3 or smaller**. The result was that **29 of 37** background
components (78%) saturated at or above 0.90, and background became the
second-highest-scoring group on the signal, above rings. Under the original
`(k-1)/(cap-1)` definition the same figure is **0 of 37**.

**The general shape of the mistake.** A ratio `part / whole` is not a
concentration measure when `whole` is small — it is a coin flip with a coarse
denominator. Concentration only means something once there is enough population
for a concentrated distribution to be distinguishable from a uniform one. Any
normalisation of the form "share of this component", "fraction of this cluster",
or "proportion of this group" inherits the defect, and it will not show up in a
mean: E5's background *mean* on the signal was 0.5901, which looks merely high
rather than degenerate. It shows up in the saturation fraction.

**What to do instead, in rough order of preference.**
1. Normalise by a global constant, as every other Tier 0 signal does
   (`(k-1)/(cap-1)` against `max_*_degree`). Scale-free and immune to this.
2. If the measure must be component-relative, use a quantity whose achievable
   range grows with size — accounts-per-distinct-attribute rather than
   share-of-accounts — so a size-2 component cannot reach the top of the range.
3. If neither is possible, floor the denominator or exclude components below a
   minimum size from the signal, and say so in the feature's docstring.

**The check that catches it.** Report the fraction of components scoring >= 0.90
normalised, broken out by group *and* by component size, not just the mean. This
is criterion 10 on any future instrument-feature experiment, and it is worth
running against any new size-normalised feature in Tier 2 before trusting it.



### RISK-003 — temporal_burst carries the top weight on a false premise

- **Status: RESOLVED.** Fixed in two parts: a feature-semantic change
  (`temporal_burst` requires same-merchant convergence, tag
  `tier0-risk003-semantic`) and a generator change (households co-burst at
  independent merchants — experiment E2, adopted as the default
  `family_coburst_shared_merchant = False`). Ring-minus-family on the design
  splits went **+0.0000 -> +0.1953**; held-out F1 0.7273 -> 0.800, precision
  0.5714 -> 0.6667, FPR 0.2609 -> 0.1739, with the non-triviality margin
  *improving* to 0.5625. Tag `tier0-risk003-resolved`.

  **Experimental chain, in order.** Each step was designed on train+validation
  only, with the record frozen to disk before the held-out split was read:

  | | ring-family | pos-below-max-neg | held-out F1 | outcome |
  |---|---|---|---|---|
  | semantic fix (Variant B) | +0.0000 | 0.9375 | 0.7273 | kept, insufficient alone |
  | E1 no household co-burst | +0.2422 | 0.2500 | 0.800 | **rejected** |
  | E2 independent merchants | **+0.1953** | **0.5625** | **0.800** | **ADOPTED** |
  | E3 overlapping merchant pools | +0.2188 | 0.2500 | 0.7619 | **rejected** |

  **Why E1 was rejected** (kept, not deleted — this is why the adopted design
  looks the way it does): E1 deletes the household co-burst outright. It buys the
  largest delta of the four, but the margin it destroys is the whole point of the
  hard negative — positives-below-max-negative collapses 0.9375 -> 0.2500 and
  family temporal activity falls to 0.0547, barely above background's 0.0034. A
  household that *never* transacts together is a weaker lookalike than one that
  does, so E1 improves the number by making the benchmark easier. Rejected on
  realism, not on the metric.

  **Why E3 was rejected:** it fails criterion 4 outright (0.2500 against a >=0.45
  bound and a no-regression-below-0.5625 bound) and regresses held-out F1 to
  0.7619. Detail and the counterintuitive mechanism are recorded below.

  **Why E2 was adopted:** it is the only variant that improves held-out
  performance *and* keeps the hard negatives hard, and its causal story is a real
  behavioural difference rather than a separability trick. Under the band
  recalibrated once on E1/E2 evidence and then frozen, it meets all eight
  criteria.

- **Original finding.** Found by the full seven-signal audit run before starting
  Tier 1 feature work.
- **Symptom:** `temporal_burst` holds the largest scorer weight (0.278) and is
  documented as "the signal that separates an abuse ring from a family sharing
  the same device". Measured on normalised values, train+validation only:
  ring 0.344, **family 0.352**, background 0.017. Families score *higher*. It
  separates rings from background (+0.327) and not at all from the hard
  negatives (-0.008), which is the distinction the benchmark exists to test.
- **Expected:** the highest-weighted signal should do the hard half of the job,
  not the easy half. Either the weight or the stated justification must change.
- **Error:** no exception. `non_triviality.signal_sign_check` reports it as
  correctly signed, because it compares positives against ALL negatives and the
  background majority masks the family collision.
- **Files involved:** `riskmesh/config.py` (weight and the SIGNALS comment),
  `riskmesh/score.py` (signal 2 and module docstring), `riskmesh/generate.py`
  (`_add_burst` and the family co-burst knobs).
- **Reproduce:** `python -m riskmesh`, seed 20260824; compare per-signal
  normalised means for ring vs family components in train+validation.
- **Suspected cause:** self-inflicted during Tier 0 tuning. Closing the
  non-triviality bounds meant raising `family_coburst_rate` 0.35 -> 0.60, setting
  `family_coburst_participation` to 0.9, and dropping
  `family_coburst_window_multiplier` from 3 to 1 -- so households now burst in
  the same 30-minute window, at nearly the same participation, as rings. The
  tuning that made the benchmark honest is what neutralised this signal.
- **Partial fix applied (feature semantics only). STILL OPEN.**
  `temporal_burst` now requires accounts to converge on the **same merchant**
  inside the window, not merely to be active in it. Measured on train+validation:

  | | before | after |
  |---|---|---|
  | ring | 0.344 | 0.297 |
  | family | 0.352 | 0.297 |
  | background | 0.017 | 0.003 |
  | **ring - family** | **-0.008** | **+0.000** |

  What this fixed: the signal no longer rewards raw traffic volume. Family
  components average 12.6 transactions per account against a ring's 9.9, so they
  were accumulating more coincidental co-occurrence; requiring a shared merchant
  strips it, and background drops nearly to zero. The feature now measures what
  its name claims.

  What this did NOT fix, and cannot: **ring-vs-family separation is still zero.**
  `_add_burst` in `generate.py` emits ring bursts and family co-bursts from the
  same code path -- same 30-minute window, same single merchant, with families at
  *higher* participation (0.9 vs 0.75). There is no coordination difference in
  the data for any feature definition to detect. Variants were measured before
  choosing: window+merchant+device -0.078, window+device -0.086, both worse; a
  15-minute window reached +0.039, rejected as a tuning knob at noise scale on
  16 positives rather than a fix.

  **Cost of the change, reported not buried:** raw single-signal F1 0.6316 ->
  0.6061 and held-out F1 0.7619 -> 0.7273 (precision 0.6154 -> 0.5714, FPR
  0.2174 -> 0.2609, one additional false positive). The old definition was partly
  earning its keep from the coincidental-density effect against background. The
  benchmark got slightly harder and more honest at the same time.

- **E1 result (train+validation design, held-out read only after the record was
  frozen to `out/experiment_e1.json`):** removing the family co-burst entirely
  (`family_coburst_rate` 0.60 -> 0.0) makes `temporal_burst` work. Ring-minus-
  family +0.0000 -> **+0.2422**; family drops 0.2969 -> 0.0547 while ring holds
  at 0.2969. Raw single-signal F1 0.6061 -> 0.7692. Held out: F1 0.7273 -> 0.800,
  precision 0.5714 -> 0.6667, FPR 0.2609 -> 0.1739. Panel stays PASS.

  **Not adopted yet, and not tagged resolved.** The cost is that the
  non-triviality margin narrows sharply: positives-below-max-negative falls
  0.9375 -> 0.2500 against a 0.20 bound, and hard-negatives-in-positive-range
  5 -> 4. The household co-burst was what made the hard negatives hard, and E1
  removes it outright rather than making it realistic. A household that *never*
  transacts together is arguably a weaker lookalike than one that does. The
  likely better mechanism is households co-occurring in time but at
  **independent merchants** -- real shared-evening behaviour, which Variant B
  correctly declines to score because it requires a shared merchant. That
  preserves the hard negative and should keep most of the separation.

- **E2 result (same frozen-record discipline, `out/experiment_e2.json`).** Keeps
  the household co-burst at its original timing and participation and changes
  only *where* it lands: each member goes to their own merchant instead of all
  converging on one. The causal story this encodes, stated plainly:

  > **Families share time because they share a household; rings additionally
  > converge on the same merchant.**

  | | r003-semantic | E1 | E2 |
  |---|---|---|---|
  | temporal_burst ring | 0.2969 | 0.2969 | 0.2969 |
  | temporal_burst family | 0.2969 | 0.0547 | 0.1016 |
  | temporal_burst background | 0.0034 | 0.0034 | 0.0034 |
  | **ring - family** | **+0.0000** | **+0.2422** | **+0.1953** |
  | positives-below-max-negative | 0.9375 | 0.2500 | 0.5625 |
  | hard negatives in positive range | 5 | 4 | 4 |
  | shared-device baseline F1 | 0.7442 | 0.7442 | 0.7442 |
  | held-out F1 | 0.7273 | 0.800 | 0.800 |
  | held-out precision / FPR | 0.5714 / 0.2609 | 0.6667 / 0.1739 | 0.6667 / 0.1739 |

  E2 matches E1's held-out performance exactly while keeping a far harder
  benchmark: positives-below-max-negative 0.5625 against E1's 0.25, and family
  temporal activity roughly twice E1's and 30x background. Households are
  audibly not silent.

  **Not adopted: it misses its own acceptance band.** Criterion 1 asked for
  ring-minus-family in +0.05 to +0.15; E2 returned **+0.1953**. Seven of the
  eight criteria pass. The band exists to catch E2 collapsing toward E1's
  confound, and on the evidence it did not -- criteria 2 and 4 both clear with
  margin -- but the number is the number, and the band is the reviewer's to
  widen, not the implementer's to reinterpret.

  **Isolation:** four of the other six signals identical to four decimals.
  `failure_refund_rate` -0.0011 and `merchant_concentration` -0.0022 moved, both
  denominator effects of the same kind seen in E1 and expected whenever the
  generator changes family transaction counts.

- **E3 result: FAILS criterion 4, not adopted.** Gave household members
  overlapping preferred-merchant sets (`family_merchant_overlap` 0.5 over a
  4-merchant household pool) on top of E2's per-member co-burst merchant.

  | criterion | target | E3 | |
  |---|---|---|---|
  | 1 ring-family delta | +0.10 to +0.25 | **+0.2188** | PASS |
  | 2 family temporal_burst non-zero | > 0.02 | 0.0781 | PASS |
  | 3 background low | 0.002-0.02 | 0.0034 | PASS |
  | 4a positives-below-max-negative | >= 0.45 | **0.2500** | **FAIL** |
  | 4b no regression below E2 | >= 0.5625 | **0.2500** | **FAIL** |
  | 5 hard-negs in positive range | >= 4 | 4 | PASS |
  | 6 shared-device baseline F1 | < 0.85 | 0.7442 | PASS |
  | 7 other six isolated to 4dp | denom effects only | 2 denom effects | PASS |
  | 8 no test before freeze | structural | structural | PASS |

  Held out: F1 0.7619, precision 0.6154, FPR 0.2174 -- worse than E2's
  0.800 / 0.6667 / 0.1739 and merely level with r001-resolved.

  **The mechanism worked and the outcome still went the wrong way.** Household
  members did become more alike: mean pairwise merchant Jaccard rose 0.196 ->
  0.260. But family `temporal_burst` *fell* 0.1016 -> 0.0781. Under E2 every
  member drew preferences from the global popularity law, so they all tended to
  hold the same few dominant merchants and coincided there; under E3 each member
  holds a random subset of a small household pool, which spreads their choices
  and makes same-minute, same-merchant collisions rarer. Making a household more
  self-similar made it less *coincident*. The hard-negative margin then collapsed
  to 0.2500, exactly E1's figure.

- **Methodological finding, worth more than E3 itself.** E3's first
  implementation drew the household pool from the main RNG stream, re-rolling
  every downstream draw and moving `instrument_sharing` by +0.070 -- an
  account-count metric that merchant preferences cannot affect. Criterion 7
  caught it. Re-implemented with a dedicated per-cluster `Random`; the band and
  mechanism were not touched. The lesson is recorded permanently in
  `experiment.py`: a generator experiment needing randomness during entity
  construction must not draw from the shared stream.

- **E2 adopted as the default.** `family_coburst_shared_merchant` flipped
  True -> False in `config.py`; nothing else changed. Verified against the frozen
  `out/experiment_e2.json`: all seven signals reproduce bit-exactly (ring,
  family, background and delta identical to four decimals on every one), panel
  PASS, 19/19 checks, pyright clean. The config fingerprint moved
  `381948e3f5dc84cc` -> `b7b069226b2299c7`, fully accounted for by the two fields
  (`family_merchant_overlap`, `family_merchant_pool_size`) added for E3 after the
  E2 run — hashing today's config without those two fields returns
  `381948e3f5dc84cc` exactly. The experiment and the default-config run are
  equivalent by measurement, not by assumption.

- **Alternatives left on the table, deliberately not taken.** Widening
  `family_coburst_window_multiplier` back out from 1, or dropping
  `family_coburst_participation` below the ring's 0.75, would also separate the
  classes — but both work by making the household *less* like a ring in timing,
  which loosens the non-triviality margin that Tier 0 tuning bought. E2 separates
  them on *where* rather than *when*, which is the difference an investigator
  would actually cite.

### RISK-004 — instrument_sharing scores families above rings — CLOSED

- **Status: CLOSED** — rejected as a production scoring signal for the current
  benchmark and ring type. Full closure statement and its scope caveat at the end
  of this entry. Filed by the same audit as RISK-003; three pre-registered fixes
  and the zero-weight fallback were run and all four failed -- see below.
- **Symptom:** normalised means, train+validation: ring 0.203, **family 0.297**,
  background 0.037. Ring minus family is -0.094 at weight 0.144, so the signal
  pushes hard negatives toward the positive band.
- **Expected:** higher on rings than on the legitimate lookalikes.
- **Error:** no exception. Masked in `signal_sign_check` for the same reason as
  RISK-003 -- the background majority dominates the all-negative mean (+0.088).
- **Files involved:** `riskmesh/generate.py` (`_inject_rings` instrument overlap,
  `_inject_families` shared card), `riskmesh/score.py` (signal 3).
- **Reproduce:** as RISK-003. Raw ranges tell the story: rings [2, 3], families
  [1, 8].
- **Suspected cause:** asymmetric injector caps, not a scoring error.
  `_inject_rings` shares one instrument across `rng.randint(2, 3)` members, so
  ring raw values cannot exceed 3, while a household of up to
  `family_size_max` (8) shares one card. Normalising by
  `(k-1)/(max_instrument_degree-1)` therefore rewards the larger family.
- **E4 result: the proposed fix was run and it does not work.** Pre-registered
  hypothesis: scale ring instrument overlap with ring size
  (`ring_instrument_share = 0.5`, replacing the flat `rng.randint(2, 3)` cap).
  One value, one result -- adjacent fractions were ruled out in advance, because
  a failed 0.5 hypothesis is a result about the mechanism, not a bad parameter.
  Record frozen to `out/experiment_e4.json` before the test split was read.

  | # | criterion | bound | E4 | |
  |---|---|---|---|---|
  | 1 | ring-family delta on `instrument_sharing` | [+0.05, +0.20] | **-0.0391** | **FAIL** |
  | 2 | ring `instrument_sharing` | >= 0.30 | **0.2578** | **FAIL** |
  | 3 | family `instrument_sharing` unchanged (hard gate) | 0.2969 +/- 0.01 | 0.2969 | PASS |
  | 4a | positives-below-max-negative | >= 0.45, no regression below 0.5625 | 0.6875 | PASS |
  | 4b | hard negatives in positive range | >= 4 | 4 | PASS |
  | 5 | `instrument_sharing` single-signal F1 | < 0.85 | 0.6286 | PASS |
  | 6 | shared-device baseline F1 | < 0.85 | 0.7442 | PASS |
  | 7 | other six signals isolated to 4dp | denom effects only | **none moved at all** | PASS |
  | 8 | held-out F1 | >= 0.800 | 0.8000 | PASS |
  | 9 | no test read before freeze | structural | structural | PASS |

  Seven of nine pass. The two that fail are the two the experiment existed to
  move: the sign does not invert. `instrument_sharing` goes from ring 0.2031 /
  family 0.2969 to ring 0.2578 / family 0.2969 -- an improvement of +0.0547 on
  the ring side, less than half of what closing the -0.0938 gap needs.

  **Why, measured rather than guessed.** Mean sharers per ring went 2.50 -> 3.04
  against a mean ring size of 6.33. The premise that a flat 2-3 cap sits well
  below half the ring is simply wrong at these ring sizes: half of 6.33 is 3.2,
  and the old rule already delivered 2.5. Python's banker's rounding costs a
  little more (`round(0.5*5) == 2`, `round(0.5*9) == 4`), but that is a detail,
  not the cause.

  The real asymmetry is not 3-versus-size, it is **50% of members against 100%
  of members**. Only 13 of 24 households share a card at all, but the ones that
  do share it across a mean of 5.31 accounts out of a mean household size of
  5.08 -- effectively everyone. Every ring shares, but only with half its
  members. Two similarly-sized groups, one sharing wholesale and one sharing
  partially, is why the household still wins.

  **Arithmetic that is deliberately not being acted on.** For the ring mean to
  clear family + 0.05 the mean sharer count would have to reach about 3.78, i.e.
  `ring_instrument_share` near 0.6. That is an in-band value and it is exactly
  the adjacent-fraction sweep that was pre-registered as forbidden, so it has not
  been run and should not be run as a fix. It would move a mean without making
  the feature discriminative: single-signal F1 moved only 0.6154 -> 0.6286 under
  E4, because the two distributions overlap by construction and a larger sharer
  count slides one mean along without separating them.

- **Domain-grounds tension, recorded because it bounds the design.** A real mule
  ring should dominate families here by a wide margin -- many accounts funded
  through few instruments is the mechanic. Modelling that faithfully means
  `ring_instrument_share` near 1.0, which makes the signal a near-separator and
  is precisely what criterion 5 and the +0.20 ceiling exist to forbid. Realism is
  being traded down to keep the benchmark honest. That trade is what makes the
  band narrow, and it is why the fix cannot simply be "share harder".

- **Status: OPEN.** The count-scaling mechanism is now a measured dead end rather
  than an untested plan. The next decision is which of two things to rethink, and
  it is a decision, not a sweep:
  1. **The feature.** `instrument_sharing` normalises max-accounts-on-one-
     instrument by a global cap (`max_instrument_degree`), so it rewards group
     size. Normalising by component size, or counting *instruments per account*
     rather than accounts per instrument, would measure concentration instead of
     headcount -- and concentration is the thing that actually differs.
  2. **The injector.** Give rings several shared instruments over many members
     (a funding pattern) rather than one instrument over a subset, so the ring's
     signature is the ratio of accounts to distinct cards rather than the size of
     the largest sharing set.

  Option 1 is the smaller change and does not touch the data, so the RISK-001 and
  RISK-003 before/after comparisons survive it. That is the one to try first.

- **Kept:** `ring_instrument_share` stays in `config.py` at its inert default
  0.0, and `run_e4` stays in `experiment.py`. The frozen record is in
  `experiments/experiment_e4.json`. Rejected-alternative provenance, not dead
  code -- it is the evidence for why the next attempt should not be another
  fraction.

- **E5 result: option 1 refuted, and it is worse than what it replaces.**
  Redefined `instrument_sharing` as the share of a component's accounts on its
  most-shared instrument (`k / component_size`) instead of `(k-1)/(cap-1)`.
  A scorer-only change, so both arms ran on byte-identical data. The prediction
  that this would fail was written into the frozen record *before* the run.

  | # | criterion | bound | E5 | |
  |---|---|---|---|---|
  | 1 | ring-family delta | [+0.05, +0.20] | **-0.2263** | **FAIL** |
  | 2 | ring `instrument_sharing` | >= 0.30 | 0.4514 | PASS |
  | 3 | other six bit-identical (hard gate) | exact | none moved | PASS |
  | 4a | positives-below-max-negative | >= 0.45, >= 0.5625 | 0.5625 | PASS |
  | 4b | hard negatives in positive range | >= 4 | 4 | PASS |
  | 5 | `instrument_sharing` single-signal F1 | < 0.85 | 0.6154 | PASS |
  | 6 | shared-device baseline F1 | < 0.85 | 0.7442 | PASS |
  | 7 | total-score ring - family | >= 0.1758 | **0.1667** | **FAIL** |
  | 8 | held-out F1 | >= 0.800 | 0.8000 | PASS |
  | 9 | no test read before freeze | structural | structural | PASS |

  Seven of nine. The delta went **-0.0938 -> -0.2263**, two and a half times
  worse, and the whole-scorer separation fell 0.1858 -> 0.1667. Held-out metrics
  did not move, which says only that the signal's weight is too small to shift
  the operating point -- not that the change was harmless.

  **Why, and it is the same reason E4 failed.** Rings share one card across a
  subset (2.50 of 6.33 members); households that share, share across everyone
  (5.31 of 5.08). Removing the group-size term does not help, because group size
  was never the thing helping rings -- it was the only thing *limiting* the
  household's score. A share-based measure lets the household reach ~1.0 and the
  ring ~0.45, which is a cleaner measurement of a difference that runs the wrong
  way.

  **A second, independent defect the experiment exposed.** Component-relative
  normalisation is degenerate on small components: `k/size` saturates at 1.0 for
  any size-2 component whose two accounts touch one instrument. **29 of 37**
  background components in train+validation are size 2, so background jumped
  0.0372 -> **0.5901** and became the second-highest-scoring group on this
  signal. Even if the ring-family direction had come out right, this definition
  would have to be rejected for that alone.

- **Where RISK-004 now stands.** Both generator-side scaling (E4) and
  feature-side renormalisation (E5) have been measured and refuted. What remains
  is not a third variant of either:

  1. **Option 2, injector-side.** Give rings *several* shared instruments across
     many members -- a funding pattern -- so the ring's signature is the ratio of
     accounts to distinct cards rather than the size of the largest sharing set.
     This changes the data, so it would need the same freeze-and-compare
     discipline as E1-E4 and would invalidate nothing already tagged.
  2. **Zero-weight it, as RISK-001 did for `ip_sharing`.** The signal currently
     runs at -0.0938 against the hard negatives at weight 0.1444: it is actively
     pushing households toward the positive band. RISK-001 set the precedent that
     a signal measuring the wrong thing should carry zero weight until it earns
     otherwise. This is a *weight* decision, so it belongs with the cost model --
     logged as D2 in `deferred_decisions.md`.

  Option 2 is the one that could make the signal genuinely work; option 2 and the
  D2 weight question are independent and can both be true.

- **Kept:** `instrument_sharing_component_relative` stays in `config.py` at its
  inert default `False`, `run_e5` stays in `experiment.py`, and the frozen record
  is in `experiments/experiment_e5.json`.

- **E6 result: option 2 inverts the sign, then over-separates.** Rings funded
  through a pool of 3 cards replacing their personal instrument, scored as
  accounts-per-distinct-instrument normalised by the global cap. Generator *and*
  feature changed together, which is a deliberate exception to one-change-at-a-
  time: a funding pool is invisible to a largest-sharing-set feature, and an
  accounts-per-card feature has nothing to find in the old injector. Either alone
  is a no-op. The record says so before the numbers.

  | # | criterion | bound | E6 | |
  |---|---|---|---|---|
  | 1 | ring-family delta | [+0.05, +0.20] | +0.1576 | PASS |
  | 2 | ring `instrument_sharing` | >= 0.30 | **0.1576** | **FAIL** |
  | 3 | other six isolated to 4dp | denom effects | none moved | PASS |
  | 4a | positives-below-max-negative | >= 0.45, >= 0.5625 | **0.0625** | **FAIL** |
  | 4b | hard negatives in positive range | >= 4 | **1** | **FAIL** |
  | 5 | `instrument_sharing` single-signal F1 | < 0.85 | **0.9697** | **FAIL** |
  | 6 | shared-device baseline F1 | < 0.85 | 0.7442 | PASS |
  | 7 | total-score ring - family | >= 0.1758 | 0.2221 | PASS |
  | 8 | held-out F1 | >= 0.800 | 0.8889 | PASS |
  | 9 | no test read before freeze | structural | structural | PASS |
  | 10a | background saturated >= 0.90 | <= 0.10 | 0.0000 (0/37) | PASS |
  | 10b | size <= 3 saturated >= 0.90 | <= 0.15 | 0.0000 (0/41) | PASS |

  The mechanism works and that is the problem. `instrument_sharing` goes to ring
  0.1576 against family **exactly 0.0000** and background 0.0034: the signal
  becomes a near-binary ring detector with single-signal F1 **0.9697**, the
  non-triviality panel verdict flips to **FAIL**, positives-below-max-negative
  collapses 0.5625 -> 0.0625 and hard negatives inside the positive range fall
  4 -> 1. Held-out F1 *rises* to 0.8889 -- the detector looks better precisely
  because the benchmark stopped being hard. This is what criterion 5 and the
  band's upper bound existed to catch.

  Criterion 10, added after E5, passed cleanly at 0/37 and 0/41: normalising by
  the global cap rather than component size avoided the saturation defect
  entirely. The new gate worked; it just was not the thing that failed.

  **One criterion was mis-specified and it is being reported, not reinterpreted.**
  Criterion 2 ("ring `instrument_sharing` >= 0.30") was carried forward verbatim
  from E4, where family sat at 0.2969 and a ring below 0.30 could not possibly
  lead. Under E6's feature the scale is different -- family is 0.0000, so a ring
  at 0.1576 already leads by the full band. The criterion as written is not
  measuring what it was written to measure. It is left as a FAIL. Rescoring a
  frozen criterion after seeing the result is the exact failure mode this
  discipline exists to prevent, and the outcome does not turn on it: 4a, 4b and 5
  fail on substance and the panel fails outright.

#### The pre-declared fallback was executed, measured, and cannot stand

Zero-weighting `instrument_sharing` and renormalising the remaining five was run
end to end. **It breaks the benchmark's own integrity gate:**

| | weighted 0.1444 | zero-weighted |
|---|---|---|
| positives-below-max-negative | 0.5625 | **0.1250** (bound >= 0.20) |
| hard negatives in positive range | 4 | **1** |
| panel verdict | PASS | **FAIL** |
| held-out precision | 0.6667 | 0.8000 |
| held-out F1 | 0.8000 | 0.8889 |
| held-out FPR | 0.1739 | 0.0870 |

Same pathology as E6, reached from the opposite direction. `instrument_sharing`'s
-0.0938 delta was the main thing holding the hard negatives up against the
positives; removing it lets them fall away. The renormalisation compounds it by
redistributing weight to `account_newness` (0.1111 -> 0.1299), which at
single-signal F1 0.9412 is the closest thing the scorer has to a lone separator.

**So the repo is left at the last known-good state**, weights unchanged, panel
PASS, held-out F1 0.800. Shipping a state whose own non-triviality gate reports
FAIL is not a defensible close, and quietly relaxing the bound to accommodate it
would be worse. This is the one point in the RISK-004 sequence where the
pre-declared plan met evidence it did not anticipate, and the evidence wins.

- **Status: CLOSED — rejected as a production scoring signal for the current
  benchmark and ring type.** `instrument_sharing` stays computed, but no longer
  stays at weight 0.1444 — Phase 11's weight search zeroed it (see the forward
  note below, and `deferred_decisions.md` D2, RESOLVED), and Task 6's re-freeze
  against the current five-ring-type benchmark reproduces the same zero weight.
  The "removing it measurably breaks the benchmark" measurement immediately
  above this line describes the *zero-weight-plus-renormalise-the-rest*
  fallback tried and rejected earlier in this entry (which redistributed its
  weight onto `account_newness` and broke the panel) — that is a different
  operation from what actually shipped: Phase 11 zeroed `instrument_sharing`
  *together with* adding `instrument_pool_concentration` as a companion
  signal, which does not break the panel (D2's Resolution has the numbers).
  Three pre-registered attempts -- generator-side scaling (E4), feature
  renormalisation (E5), funding-pool mechanism (E6) -- were run and rejected as
  fixes to `instrument_sharing` itself; that is what stays rejected. No
  further variants. Tracked as **D2** in `deferred_decisions.md` for the
  weight/cost stage, RESOLVED there.

  **Scope of this closure, stated explicitly so it is not over-read.** What was
  rejected is instrument sharing *as a discriminative signal against this
  benchmark's hard negative, for Tier 0's single shared-device ring type*. It is
  **not** a finding that instrument intelligence is useless for coordinated-abuse
  detection, and nothing here should be quoted that way.

  The reason the signal cannot work here is specific and it is a property of the
  generator, not of the domain: Tier 0's ring shares **one** card across a subset
  of members, and its hard negative -- a household -- shares **one** card across
  all of them. Two mechanisms that differ only in what fraction of a
  similarly-sized group shares a single instrument. That is the entire reason
  every measure of it favours the household.

  A **multi-card ring type** breaks that symmetry, and E6 is the evidence: when
  rings were funded through a pool of cards, accounts-per-instrument separated
  the classes immediately and in the right direction (+0.1576, family exactly
  0.0000). E6 was rejected for over-separating *this* benchmark, whose only
  positive class is the shared-device ring -- not because the feature failed. If
  Tier 1 or Tier 2 adds a funding-network ring type alongside the existing one,
  this signal should be revisited from E6's design, and the record in
  `experiments/experiment_e6.json` is the starting point rather than a dead end.

- **Kept:** `ring_instrument_pool_size` (0) and
  `instrument_sharing_accounts_per_card` (False) stay in `config.py` inert,
  `run_e6` stays in `experiment.py`, record in `experiments/experiment_e6.json`.

- **Forward note, Phase 10/11 — revisited from E6, exactly as this closure
  statement's own scope caveat pointed to.** Phase 10 added a real
  funding-network ring type: a configurable fraction of rings
  (`p_ring_instrument_funded`, tuned to 0.7) are now pool-funded through a
  small shared-instrument pool (`ring_instrument_pool_size = 4`) instead of the
  flat 2-3-sharer partial overlap, alongside the minority of rings left
  unchanged. A new always-on signal, `instrument_pool_concentration`, scores
  it — accounts-per-distinct-instrument in the pool, the same mechanic E6
  measured, but applied to a majority-but-not-all fraction of rings rather
  than all of them, which was the failure mode E6 was rejected for
  (over-separating a benchmark whose only positive class was the device ring).

  **Measured, the same way RISK-003's tables were: rescoring and comparing
  per-signal means on train+validation.** `instrument_pool_concentration`
  reads ring **0.0755**, family **0.0000**, background **0.0000** — a
  ring-minus-family delta of **+0.0755**, single-signal F1 **0.72**, and
  the sign is correct on both comparisons that matter (ring > family, ring >
  background) instead of RISK-004's -0.0938. The new signal does not merely
  avoid RISK-004's pathology, it discriminates positively where the old one
  discriminated against.

  **`instrument_sharing` itself changed too, as a side effect of the same
  generator change, and it is worth naming since it is not the fix.** The
  hybrid rings' altered card patterns shifted `instrument_sharing`'s own
  ring/family means to ring 0.2109, family 0.2031 — the delta flipped from
  RISK-004's -0.0938 to a near-zero **+0.0078**. It is no longer actively
  harmful, but it is not the signal doing the separating work either; that is
  `instrument_pool_concentration`.

  **The weight search agrees, on its own criterion.** Phase 11's re-run
  weight search (`weight_search_protocol.md` §8) selected `D_drop_flagged` —
  which zeros `instrument_sharing` and `merchant_concentration` — over
  `A_baseline`, winning the difficulty-gate tie-break with a *sharper*
  `positives_below_max_negative` (0.625 vs 0.5625) than the incumbent it
  replaced, while `instrument_pool_concentration` keeps a non-trivial weight
  (0.1481) in the resulting vector. So the new signal measurably helped rings
  separate from families on this dimension, confirmed two ways: directly (the
  per-signal delta above) and indirectly (an independent cost-driven search
  chose to keep it weighted while zeroing the signal that used to fight it).

  **RISK-004 stays CLOSED.** This is a forward note recording that its own
  "next attempt should restart from experiment_e6.json" pointer was followed
  and worked, not a reopening. See `deferred_decisions.md` D2, closed in the
  same phase for the weight-side half of this story.

### RISK-002 — merchant_concentration is mis-signed — RESOLVED BY WEIGHT

- **Status: RESOLVED BY WEIGHT, not by fixing the feature.** Weight has been
  **0.00** since Phase 11's `D_drop_flagged` fold-back (the same weight
  search that zeroed `instrument_sharing`, `deferred_decisions.md` D2), and
  Task 6's re-freeze against the current five-ring-type, four-hard-negative-
  type benchmark reproduces the same zero weight for
  `merchant_concentration` (`experiments/weight_policy.json`,
  `A_baseline`/`D_drop_flagged`/`E_drop_temporal` all agree). It no longer
  contributes to the score in any direction, correct or otherwise. This entry
  used to read "OPEN, deferred" quoting weight 0.0889 and delta -0.0515 —
  both stale since Phase 11; resolved against the current numbers below,
  per Task 8's brief.
- **Symptom, as originally found and still true of the feature itself,
  updated to current data:** on normalised values (train+validation, current
  benchmark, `out/integrity_report.json` -> `non_triviality.signal_sign_check`),
  `merchant_concentration` means **0.2725** on positives against **all
  negatives** (family + office + hostel + retail + background) **0.3141**,
  delta **-0.0416**. At weight 0.00 the `weighted_contribution` is 0.00 —
  the sign no longer matters to the score, but the underlying feature is
  still mis-signed exactly as originally found. This is the ring-vs-all-
  negatives comparison `signal_sign_check` and the panel's
  `no_weighted_signal_mis_signed` gate both use (and why that gate's FLAG
  list is empty: it only inspects weight > 0 signals).

  **Not the same number as the ring-vs-family delta**, still — this is the
  same trap RISK-003 named and D1's closure re-confirmed on a different
  signal (`device_sharing`). Ring-minus-**family only**, current data
  (`out/components.csv`): ring 0.2725, family 0.2258, delta **+0.0467** —
  the opposite sign from the all-negatives comparison, driven by
  background's small mean component size (a small component's top merchant
  naturally holds a large share of few transactions) rather than by family.
- **Expected:** a weighted signal should be higher on positives. Moot now
  that the weight is 0.00.
- **Error:** no exception. `non_triviality.signal_sign_check` in
  `out/integrity_report.json`, and the `no_weighted_signal_mis_signed` FLAG row
  (empty on the current run, since it only lists weight > 0 signals).
- **Files involved:** `riskmesh/score.py` (signal), `riskmesh/config.py` (weight,
  now 0.00 via `_default_weights()`'s fold-back, not a dedicated fix).
- **Reproduce:** `python -m riskmesh`, seed 20260824.
- **Suspected cause (unchanged, the feature itself was never touched):** ring
  members inherit the ordinary sticky-merchant behaviour from `_new_account`;
  the ring injector adds a burst at one merchant but does not otherwise
  concentrate spend. Small background components' top merchant naturally
  carries a larger share of few transactions. Same shape of defect as
  RISK-001, an order of magnitude weaker.
- **Fix:** none applied to the feature. The weight search's cost-driven
  selection zeroed it as a side effect of a different objective (the same
  mechanism D2 describes for `instrument_sharing`), which resolves the
  scoring harm without resolving whether ring cash-out concentration should
  be injected at all — that generator-scope question remains genuinely open
  but is no longer urgent while the weight is 0.00.

### RISK-001 — ip_concentration is scored with the wrong sign — CLOSED

- **Status:** CLOSED. Resolved by redefinition plus zero weight; see Fix.
- **Symptom:** `ip_concentration` separates the classes in the *inverted*
  direction — low values indicate abuse, high values indicate legitimacy. Its
  best achievable single-signal F1 on train+validation is **0.9697**, reached at
  `ip_concentration <= 0.234`. Raw distributions: positives mean 0.161, negatives
  mean 0.540 — 3.3x higher on the legitimate clusters.
- **Expected:** a signal carrying positive weight in the scorer should be higher
  on positives than on negatives. This one is the reverse.
- **Error:** no exception. Surfaced by the both-directions fix to
  `single_signal_f1`; a `>=`-only sweep reported it as 0.3765 and hid it.
- **Files involved:** `riskmesh/score.py` (signal definition and weight),
  `riskmesh/config.py` (`weights["ip_concentration"] = 0.10`).
- **Reproduce:** `python -m riskmesh`, seed 20260824; read
  `out/integrity_report.json` -> `non_triviality.single_signal_detail`.
- **Suspected cause:** Tier 0 injects shared-*device* rings while the family hard
  negatives share a home *IP*. So IP concentration is a property of the
  legitimate clusters in this slice, not the abusive ones. The signal is not
  wrong in general — shared-IP concentration is a real production risk signal —
  but with only one ring type present it points the wrong way.
- **Scorer weight:** was +0.10, now **0.00** — see Fix. At the old weight it
  subtracted 0.0378 from a total positive-vs-negative score separation of 0.2009,
  degrading the scorer by roughly 19%.
- **Root cause (investigated, not assumed):** two separable things.
  1. *Real structural difference.* `_inject_rings` never touches `home_ip`;
     ring members keep per-account IPs. Max accounts on one non-common IP is
     exactly 1.00 for all 24 ring components (0% have >=2) against 4.94 for
     families (100% have >=2). Tier 0 places NO ring information in the IP
     dimension. This is not the `ring_shared_device_share` mechanism — that
     knob governs devices only and never reaches `home_ip`.
  2. *Definitional defect.* The signal measured transaction SHARE on the top
     IP rather than ACCOUNTS sharing an IP, unlike its device and instrument
     siblings. That made it a back-door ring detector: rings 0.162 (private
     IPs, so top IP holds ~1/n of traffic), background 0.462 (small
     components), families 0.701 (= p_home_ip 0.70 exactly). So
     `ip_concentration <= 0.234` meant *large component whose members share
     no IP* — Tier 0's ring definition, reached via the ABSENCE of a family
     marker. Not a size proxy: controlling for size the gap is flat at every
     size 4-8 (ring 0.12-0.22 vs family 0.64-0.73), and pure 1/size reaches
     only F1 0.727 against this signal's 0.970.
- **Fix:** redefined as `ip_sharing` = max distinct accounts on one
  non-common IP, symmetric with `device_sharing` and `instrument_sharing`,
  which drops its back-door power from 0.9697 to 0.4638. Weight set to
  **0.00**; the other six renormalised to sum to 1.00, preserving their
  relative ratios. Inversion was rejected: it would encode 'not sharing
  infrastructure is suspicious', a fit to this generator config rather than a
  risk concept, and would flip again when Tier 1 adds shared-IP rings.
  Dropping it entirely was rejected: the redefinition is correct and Tier 1's
  shared-IP ring type will make it discriminative, so it stays computed as
  investigator evidence at zero weight.
- **Covered by:** `non_triviality.signal_sign_check` and the
  `no_weighted_signal_mis_signed` FLAG row, which turn this bug class into a
  standing check rather than a one-off discovery.
- **Measured effect** (same data, scorer only; test read after the threshold
  was re-frozen on validation): held-out precision 0.5333 -> 0.6154, F1
  0.6957 -> 0.7619, FPR 0.3043 -> 0.2174, recall and ring recovery unchanged
  at 1.0 and 8/8. Panel verdict PASS before and after.

### B1 — background components all land in the train split

- **Symptom:** `python -m riskmesh.split` reports unlabelled components as
  train 27 / validation 8 / test 0. The test split contains only the 4 injected
  rings and 5 family clusters, so held-out precision is quantised to quarters and
  false-positive rate to fifths.
- **Expected:** background (unlabelled) components spread across all three
  splits, giving the test split a negative population large enough for a
  meaningful false-positive rate. `testing.md` Phase 8 requires >=1 negative
  component in test; that passes on families alone, which is why the checklist
  did not catch this — the row was too weak, not wrong.
- **Error:** no exception. Found by reading the Phase 6 split report.
- **Files involved:** `riskmesh/generate.py` (background emission window),
  `riskmesh/split.py` (median-timestamp assignment for unlabelled components).
- **Reproduce:** `python -m riskmesh.split`, seed 20260824.
- **Suspected cause:** background accounts emit across the entire 30-day window,
  so the median transaction of nearly every background component falls near day
  15, which is inside train (days 0–18). The split logic is correct; the
  generator gives it nothing to spread.
- **Fix:** give each background account a contiguous activity window
  (`bg_active_days_min/max`) instead of transacting across all 30 days. Real
  accounts have activity spells rather than uniform lifetime traffic, so the
  medians spread naturally across the window. Labelled clusters are unaffected —
  they were already period-confined. Covered by a strengthened `testing.md` row:
  every split must hold >=1 *unlabelled* component, not merely >=1 negative.
