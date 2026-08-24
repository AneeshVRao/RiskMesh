# RiskMesh — bug log

One entry per bug, newest at the top. Fill in **every** field before touching
code — the point of this file is to reason about a fix rather than guess at one.
Delete an entry once its fix is verified by the matching `testing.md` row.

Open bugs: 1 deferred (RISK-001). 1 closed (B1).

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

### RISK-001 — ip_concentration is scored with the wrong sign

- **Status:** DEFERRED to Tier 1 feature validation. Not touched during Tier 0.
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
- **Fix:** deferred. Tier 1 feature validation should decide between inverting
  the sign, dropping the weight to zero, or leaving it and letting the
  shared-IP ring type (which Tier 1 introduces) restore the intended direction.
  Changing it during Tier 0 would mean re-tuning the generator against the
  non-triviality panel, which the Tier 0 time cap explicitly forbids.

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
