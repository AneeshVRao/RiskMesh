# RiskMesh — bug log

One entry per bug, newest at the top. Fill in **every** field before touching
code — the point of this file is to reason about a fix rather than guess at one.
Delete an entry once its fix is verified by the matching `testing.md` row.

Open bugs: 1 deferred (RISK-002). 2 closed (RISK-001, B1).

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
- **Fix:** deferred. The magnitude is small (-0.0041 of a +0.2652 total
  separation, ~1.5%) and resolving it means deciding whether ring cash-out
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
- **Current scorer weight:** **+0.10**, unchanged. The signal actively pushes
  negatives up and positives down at that weight.
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
