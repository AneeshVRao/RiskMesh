# RiskMesh — bug log

One entry per bug, newest at the top. Fill in **every** field before touching
code — the point of this file is to reason about a fix rather than guess at one.
Delete an entry once its fix is verified by the matching `testing.md` row.

Open bugs: 2 deferred (RISK-002, RISK-004). 3 closed (RISK-001, RISK-003, B1).

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

### RISK-004 — instrument_sharing scores families above rings

- **Status:** OPEN. Filed by the same audit as RISK-003; the proposed
  generator-side fix was pre-registered, run as E4, and **failed** -- see below.
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

### RISK-002 — merchant_concentration is mis-signed

- **Status:** OPEN, deferred. Surfaced by the sign check added while closing
  RISK-001. Reported as FLAG, not FAIL — see below.
- **Symptom:** on normalised values (the numbers that enter the score),
  `merchant_concentration` means 0.2483 on positives against
  0.2998 on negatives, delta -0.0515. At weight
  0.0889 it contributes -0.0046 — the wrong direction.
- **Expected:** a weighted signal should be higher on positives.
- **Error:** no exception. `non_triviality.signal_sign_check` in
  `out/integrity_report.json`, and the `no_weighted_signal_mis_signed` FLAG row.
- **Files involved:** `riskmesh/score.py` (signal 7), `riskmesh/config.py` (weight).
- **Reproduce:** `python -m riskmesh`, seed 20260824.
- **Suspected cause:** ring members inherit the ordinary sticky-merchant
  behaviour from `_new_account`; the ring injector adds a burst at one
  merchant but does not otherwise concentrate spend. Background components
  are small (mean 2.17 accounts), so their top merchant naturally carries a
  larger share of few transactions. Same shape of defect as RISK-001 but an
  order of magnitude weaker.
- **Fix:** deferred. The magnitude is small (-0.0046 of a +0.2653 total
  separation, ~1.7%) and resolving it means deciding whether ring cash-out
  concentration should be injected at all — a generator scope question for
  Tier 1, not a weight tweak. Not touched while closing RISK-001, to keep
  that change's before/after comparison attributable to one cause.

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
