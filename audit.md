# Audit -- Task 10, the React investigator console, 28 files . 2026-09-05 (backfilled 2026-09-05)

**This entry is being written now, as part of the final whole-branch review fix wave, specifically
because Task 9 restored the audit ritual and correctly wrote an entry for Tasks 1-8, but Task 10
(the largest single addition on this branch) shipped after it with no entry of its own** -- the
same discipline lapse Task 9 exists to fix, recurring immediately for the one task best positioned
to need it. Reconstructed, like every "(backfilled)" entry in this file, from the implementer's own
Task 10 implementation report and task brief -- session-local planning artifacts, not committed to
git, so not cited here by path -- cross-referenced against git history `bc04231`..`fac1b3c`
(2026-09-05). Every figure quoted was cross-checked against that report and, where a plain count was
checkable independently, against `git diff --stat` run directly in this session.

## What was built

Six commit groups plus a same-day review-fix round, all confined to a single new top-level
directory:

- **`732da00`..`0cdbf2d`** (Task 10, groups 1-5): scaffolded a React console under `frontend/` and
  built its four PRD Primary Screens -- Risk Control Center (`ControlCenter.tsx`), Ring Details /
  Investigator (`Investigator.tsx` + `RingGraph.tsx` + `ActionBar.tsx` + `ExplainPanel.tsx` +
  `AuditTrail.tsx`), Threshold & Cost Analysis (`Threshold.tsx`), Evaluation / Benchmark
  (`Benchmark.tsx`).
- **`9ea6487`** (group 6): build verification, `frontend/README.md`, run instructions.
- **`fac1b3c`** (same-day review fix): three rendering gaps found and closed -- see below.
- **Stack decision**: Vite 8.2.2 + React 19.2.8 + TypeScript 5.9.3 + Tailwind v4 (`@tailwindcss/vite`,
  the Vite plugin form, not PostCSS) + `react-router-dom` 7.18.3 + `@phosphor-icons/react` 2.1.10,
  every version exact-pinned. TypeScript deliberately pinned to 5.9.3 rather than the
  newly-registered 7.0.2 native rewrite -- too fresh to trust for a project this size; every other
  pin is simply the exact version current when Task 10 landed. Four runtime dependencies total
  (`react`, `react-dom`, `react-router-dom`, `@phosphor-icons/react`); no animation library, no
  global state library, no data-fetching library -- a single ~40-line `useFetch` hook covers every
  screen's load/error/reload need. `git diff --stat bc04231..fac1b3c -- frontend/` (re-run in this
  session): 28 files changed, 4,041 insertions, of which 1,677 lines are the generated
  `package-lock.json` -- roughly 2,400 hand-written lines across app code and config.
- **The ported graph**: `RingGraph.tsx` reproduces `mockups/api.js`'s `renderGraph()` column math,
  cubic-bezier edge formula, edge-thickness-by-transaction-count formula, and alt-text sentence
  construction verbatim; only the rendering mechanism changed (JSX element construction in place of
  `innerHTML` string-building). No behavioral deviation from the original was found or introduced.
- **No backend change of any kind.** `git diff --stat bc04231..HEAD` (per the report, re-verified in
  this session) shows every changed file under `frontend/`; nothing under `riskmesh/`, `tests/`,
  `experiments/`, `requirements.txt`, or any pre-existing `.md` was touched by Task 10 itself.
  `mockups/` was deliberately kept, not retired -- the task brief's done-condition required the four
  screens to render against the live API, not a feature-parity audit against `mockups/`'s own five
  Playwright verify scripts, and `mockups/index.html`'s landing page has no React equivalent in
  scope.

## The one Important finding, and two sibling gaps volunteered in the same round

Coordinator review of Task 10 found **one Important finding**: `Threshold.tsx`'s sweep table
rendered only `false_positive_rate`/`false_negative_rate`, silently dropping the count half of the
six PRD-named sweep columns even though `SweepRow` already typed both `false_positive_count`/
`false_negative_count` and the API already returned both. Root cause was plain omission -- the
adjacent "Reviews" column already used the correct `{count} ({rate})` pattern; it simply was not
copied to the FP/FN columns. Fixed by applying that exact pattern to both.

Per the coordinator's request, the implementer then audited the other three screens for the same
class of gap -- a typed field the API returns and `mockups/` renders, that this port silently
dropped -- rather than a general re-audit, and volunteered two more:

- **`AuditTrail.tsx`** was missing `config_fingerprint` and the evidence snapshot's `summary.size`/
  `summary.n_txns`, both rendered by `mockups/api.js`'s `renderAudit()`. Fixed with one added line.
- **`Benchmark.tsx`** never rendered `/benchmark`'s `secondary` (account-level) metrics block at
  all, only `primary` (component-level) -- `testing.md` names both as required. Fixed with one added
  paragraph and a concrete TypeScript type for `secondary` in place of `Record<string, unknown>`.

(`Threshold.tsx` also gained a paragraph rendering `costs.inputs_from_data`, the same class of gap,
found in the same pass.)

All three fixes were re-verified live against the running API, not just read back from the diff:
the sweep table's first row rendering `77 (100.00%)` / `0 (0.00%)` with headers reading "FP
count/rate" / "FN count/rate"; a freshly recorded audit entry rendering `cfg fdf4fc217347d36b` and
`9 accounts · 97 txns` inline; the Benchmark secondary block rendering `precision 0.6269 · recall
0.7568 · F1 0.6857 · FP rate 16.13% · tp/fp/tn/fn 84/50/260/27`. `npm run build` clean after the
fix (89.03KB gzipped, up from 88.70KB).

## Live-verification method

Not a code read: the implementer drove the running app with the Claude Browser tool against both
the Vite dev server and, for performance numbers, the `vite preview` production build, backend
started separately (`python -m uvicorn riskmesh.api.main:app --port 8000`, on-disk artifacts,
config fingerprint `fdf4fc217347d36b`). Three methods stand out:

- **Network-traced writes.** The Investigator's "Watch" action was confirmed via
  `read_network_requests` and DOM inspection to be a real `POST /rings/{id}/review` followed by the
  server's re-read of `/rings/{id}/evidence` -- the button disabled itself because the server's
  fresh audit array contained the action, not because of client-side state set at click time.
- **An `/explain`-failure monkey-patch.** `window.fetch` was monkey-patched in the live page to
  reject any request containing `/explain`, then a different component was opened client-side. The
  panel's degraded text was extracted directly from the DOM ("Explanation unavailable —
  deterministic evidence below is unaffected"), while the graph, score, and evidence table were
  confirmed to render normally alongside it -- structurally impossible for `/explain` to gate the
  rest of the screen, not merely "handled gracefully" by convention.
- **A line-by-line graph-port diff against the original**, comparing `RingGraph.tsx` against
  `mockups/api.js`'s `renderGraph()` formula by formula (column math, edge curve, edge thickness,
  alt-text), not just a visual screenshot match.

Performance was measured via the Resource Timing API (`performance.getEntriesByType('resource')`)
against the production build, after an earlier wall-clock-polling measurement was found to be
inflated by `setTimeout` throttling in the automated browser tool's background tab -- a
measurement-methodology correction made and disclosed within the same task, not carried forward
uncorrected. Risk Control Center's three parallel fetches completed by 144ms (target 3s);
Investigator's evidence read completed by 139ms with `/explain` completing independently at 200ms
(target 2s).

## Still open

Nothing new. `mockups/` retirement remains an explicit non-decision (see Task 10's own report,
"mockups/ retirement recommendation") -- neither this task nor Task 8 decided to deprecate it, so
the README, corrected in this same review-fix wave, describes both clients rather than implying one
is superseded. `frontend/README.md` also cited a session-local planning-artifact path that dangles
on a clean clone (nothing under `.superpowers/` ships with the repo); corrected in this same
review-fix wave to describe the source in prose instead.

---

# Audit -- Tasks 1-8 of `integrity-and-scope-closure` complete, the audit ritual itself restored . 2026-09-05

**This entry is being written now, as Task 9 of the same plan, specifically because no entry was
written as any of Tasks 1-8 closed** -- the exact discipline lapse this file's own restoration
exists to fix. It is therefore a reconstruction like every entry below it, not a same-day read
taken during the work. Assembled 2026-09-05 from the plan's own review ledger (a session-local
planning artifact, not committed to git, which records every review, ruling and finding as it
happened -- the closest thing to a contemporaneous record that exists), the per-task implementer
reports for Tasks 1, 2, 3, 4, 6, 7 and 8 (same status; there is no Task 5 report, see below), and
git history on this branch from `9c31f15` through `e9f3d6b` (2026-08-31 through
2026-09-01). Every figure quoted was cross-checked against the current frozen records in
`experiments/` and a live `out/`, config fingerprint `fdf4fc217347d36b`, confirmed in this session
(`Config().fingerprint()` run directly, matching `out/eval_report.json`).

## What was built

Nine tasks against the `integrity-and-scope-closure` plan (a session-local planning document, not
committed to git -- see the git log on this branch, `9c31f15` through `e9f3d6b`, for the actual
work it describes), closing prior audit
findings #12, #15, #16, #18, #19 and (this entry) #23, plus PRD-compliance and panel-design gaps
the original audit missed entirely (D4, D5, RISK-005 below):

- **Task 1** (`9c31f15`..`d7bc37f`): `riskmesh/freeze.py`, regenerating all four frozen protocol
  records deterministically; a new fifth test suite `tests/test_freeze.py`.
- **Task 2** (`6242c44`..`684c748`): six bare `assert`s in the design-split guards converted to a
  raised `DesignSplitViolation(AssertionError)` so they survive `python -O`; the artifacts
  fingerprint map widened 7 -> 9 files; a false gate-provenance claim in `costmodel.py` corrected
  (see below).
- **Task 3** (`7421636`..`eeec047`): four new ring types (`ip`, `instrument`, `refund`, `hybrid`)
  plus the population raise absorbed from Task 5; fingerprint `c3ee14627c2c2ce2` ->
  `7314e7e534ea4b11`.
- **Task 4** (`c860893`..`9a8405a`): three new hard-negative cluster types (`office`, `hostel`,
  `retail`), `Label.cluster_type` and `Candidate.cluster_id` threaded through the API, closing
  audit #16 (split isolation for clusters, not just rings); fingerprint `ee7ab3c7439b7dc8` ->
  `28e054e8fa8436e9`.
- **Task 5**: closed by controller ruling, no dispatch -- see below.
- **Task 6** (`12c012a`..`0c3b61b`, 9 commits): all four protocols (weight, abstention, XGBoost,
  GraphSAGE) re-frozen and re-run against the five-ring-type, four-hard-negative-type benchmark;
  fingerprint folded to `fdf4fc217347d36b`.
- **Task 7** (`b92191e`..`dab9d14`): XGBoost/GraphSAGE baseline rows, a 101-row threshold sweep,
  and bootstrap confidence intervals added to `riskmesh/comparisons.py`; a live-console crash
  fixed (see below).
- **Task 8** (`fdf65cb`..`e9f3d6b`, 5 commits): `README.md`, `testing.md`, `experiments/README.md`,
  `PRODUCT.md` and `implementation_plan.md` brought current against the Task 6/7 re-freeze; D1
  closed with evidence; two new findings (D5, RISK-005) surfaced and documented rather than
  patched.

**Task 5 was closed without a dispatch.** Its substance (raising `target_txns` and the
population) had already been folded into Task 3 by an earlier ruling, so the controller verified
every one of its done-conditions directly against the post-Task-3 `out/` rather than spending an
implementer seat re-deriving already-true facts (`progress.md`, Task 5 entry): 19,310 transactions
(> 10,000, inside the PRD's 10-25k demo range), panel PASS, pbmn 0.7708 (>= 0.45 gate),
hard-negatives-in-range 69 (>= 4), shared-device-only baseline F1 0.4961 (< 0.85 bound), largest
component share 0.0043 (< 0.15 bound), every split holding both positives and unlabelled
negatives. There is accordingly no `task-5-report.md`.

## Compared against the plan

The plan's own review ledger records a preflight scan that identified five
cross-task conflicts and five per-task self-consistency risks before any implementer ran, and
resolved each with a numbered ruling (R1-R5) before work started -- G4 (protocol frozen before any
candidate is scored) is verified in the git log itself: every one of the four Task 6 re-freeze
commits (`12c012a`, `478d323`, `2a5719d`, `e2bb0f0`) lands before its matching run commit
(`08bbb6c`, `85a17fe`, `b5fcd21`, `63bc17a`) -- stronger than the per-protocol ordering the rule
required, since all four freezes land before all four runs. All five suites (`test_riskmesh.py`,
`test_ml.py`, `test_gnn.py`, `test_freeze.py`, `test_api.py`) were green at Task 8's close.

## Corrections and defects surfaced -- reported plainly, because that is what this ritual is for

This plan's own review loop caught controller-introduced errors at least four times across Tasks
2, 3, 4 and 7. Each is stated here as what actually happened, not softened into "issues were
resolved along the way."

**Task 2 -- a false claim, corrected, and the first correction was itself imprecise.** The
original whole-repo audit's most severe finding was that `costmodel.py`'s docstring falsely
claimed the panel/difficulty gates were written before `select_weights()`'s real implementation,
when in fact `git show 96ae30f:riskmesh/costmodel.py` showed both landing in the same commit
(`9cafa71`). Task 2's implementer rewrote the provenance paragraph -- and review found that
rewrite still imprecise: it had not checked what `select_weights()` actually *was* in `96ae30f`,
only that the name existed. The controller verified directly (`git show
96ae30f:riskmesh/costmodel.py`) that it was a deliberate stub raising `NotImplementedError("Not
run. The protocol is frozen in weight_search_protocol.md and awaiting confirmation before any
candidate is scored.")` -- meaning the search was structurally prevented from running before the
freeze was confirmed, the opposite of what the imprecise correction implied was in doubt. A second
fix round rewrote the paragraph to lead with the stub and state plainly that gate-vs-implementation
ordering between the panel gate (present in `96ae30f`) and the two difficulty gates (added only in
`9cafa71`, alongside the real implementation) is unprovable in either direction, rather than
asserting either one. Two rounds to get one docstring paragraph honest -- exactly the review loop
working as intended, not evidence it works on the first pass.

**Tasks 3 and 4 -- the same controller spec defect, twice.** Task 3's brief described the
refund-abuse ring type by behavioural mechanism only ("weak-to-absent infrastructure sharing").
`graph.py` links components structurally (device/IP/instrument edges only; merchants deliberately
never link), so all 12 refund rings reduced to graph singletons and produced **zero** scoreable
candidates -- invisible to all 27 passing checks because none asserted that a declared ring type
ever yields a positive candidate. Review caught it; the fix gave refund rings a structural
instrument edge, raising `n_positive` from 40 to 47 with zero new random draws. Task 4 repeated the
identical mistake in the same task: retail-chain clusters were specified as a merchant-convergence
collision, but merchants do not link, so 4-8 of each cluster's 6-10 members were dropped as
singletons (initial coverage 28%, only 2 of 10 candidates in the positive range). Review caught it
again; the fix gave every member a shared instrument from a small pool, raising mean coverage to
93.65%. A Global Constraint (G6b) was added to the plan after the second occurrence: any injected
population needs an explicit structural edge or it exists only in `labels.csv`.

**Task 7 -- an incoherent operating-point pairing, shipped, and caught downstream.** The
controller's own brief stated "Tier 1's [numbers] are F1 0.75 and expected loss 92,263.55." Those
two figures come from two different frozen records at two different thresholds:
F1 0.75 is `baselines.json`'s `ring_score` row at its own F1-selected validation cutoff (0.22);
92,263.55 is `weight_policy.json`'s `held_out` block at the cost-selected threshold (0.10), where
F1 is actually 0.5432. The pairing reached the implementer's report and a test assertion before the
implementer's own flagged concern surfaced it. The fix: every metric in the baselines table now
carries the threshold and selection metric it was measured at as a field, and check 25 gained an
adversarial assertion that `tier1_reference["f1"]` must **not** equal `ring_score`'s F1, so the
mispairing cannot silently recur. A **separate** Critical was found in the same task, by a
reviewer running the live stack in a browser rather than reading code: `mockups/api.js:647` sorted
the new 7-row baseline table with `y.held_out.f1 - x.held_out.f1`; the new `xgboost_scorer` row has
`held_out: null` by design (no feasible candidate, no read permitted), so the comparator threw
`TypeError: Cannot read properties of null`. `initBenchmark()`'s top-level `.catch` swallowed it,
and the console silently fell back to its pre-Task-7, hardcoded 5-row placeholder with an "API
offline" banner, while the API itself served correct 7-row data underneath. Invisible to all five
green Python suites, because nothing tests `mockups/api.js`. Fixed the same task (comparator treats
`null` as sinking to the bottom, not throwing) rather than deferred to the eventual React rewrite,
because `mockups/` is named "the live client" and the PRD's Fallback Demo Path depends on it.

## D1 closed, D4 and D5 opened, RISK-005 filed -- the headline findings of Task 8's sweep

**D1 (temporal_burst redundancy, open since Tier 0) is now closed with a real result, not a
tie.** Task 6's re-run weight search found `E_drop_temporal` (zeros `temporal_burst`) beating the
prior incumbent outright on validation expected loss (43,331.85 vs 57,601.30), clearing both
difficulty gates with room to spare. Folded back per protocol into `Config()._default_weights()`;
a second pass reached a fixed point (`A_baseline`, `D_drop_flagged`, `E_drop_temporal` now describe
the identical vector). `temporal_burst` ships at weight 0.0000. The mechanism is not the one D1's
own hedge anticipated (a second bursting ring type making the signal *more* useful) -- what was
measured instead is a mixture effect: `temporal_burst` separates rings well against each hard-
negative type individually but only weakly against all four combined at one global threshold.

**D4 (new, disclosed rather than fixed): the shipped operating threshold is F1-selected, not
loss-selected, contrary to a PRD Must-have.** Discovered during Task 7/8 prep, missed by the
original audit, which verified a cost model existed and a threshold was frozen before the test
read but never checked which metric the shipped threshold optimises. `out/threshold.json` selects
by maximum F1 on validation (`"selection_metric": "f1"`, printed in the file); PRD.md's own worked
example states plainly "We do not choose the threshold that maximizes F1." A genuinely loss-
selected threshold already exists and is frozen (`weight_policy.json`'s `held_out` block, threshold
0.10) -- the gap is that the pipeline's headline number and everything the console displays comes
from the other procedure. By controller ruling, not fixed here: switching the selection metric
would move every headline number a documentation sweep just wrote down a second time, and is
scoped modelling/product work. Filed as `deferred_decisions.md` D4.

**D5 (new, disclosed rather than fixed): no weight-search candidate re-enables `ip_sharing`.**
`ip_sharing` was correctly zeroed under RISK-001 in Tier 0, before any IP-type ring existed. Task 3
added a real shared-IP ring type; the five weight-search candidates (`A`-`E`) were declared before
Task 3 existed and none re-introduces the signal (`A`/`D`/`E` zero it identically to the pre-
Task-3 vector; `B`/`C` are refused by the difficulty gate before their weight on it matters). The
measured cost, verified by grouping the current held-out test split by `ring_type`: `ip`-type
rings are the scorer's one clear weak spot, 1 of 4 caught -- the worst recall of any ring type, and
the only one where the naive `transaction_level` baseline does better. Filed as
`deferred_decisions.md` D5.

**RISK-005 (new): `device_sharing`, the largest weight in the scorer (0.3929), is mis-signed
against two of four hard-negative types.** Surfaced during Task 8's documentation sweep and
extended by controller investigation. `signal_sign_check`'s pooled ring-vs-all-negatives view
reports it "ok" (delta +0.0468), but that pools 176 train+validation negatives together and masks
the per-cluster-type picture:

| cluster type | n | ring 0.1837 vs type | delta |
|---|---|---|---|
| family | 40 | 0.3523 | **-0.1686** (badly mis-signed) |
| office | 10 | 0.2636 | **-0.0799** (mis-signed) |
| hostel | 10 | 0.0000 | +0.1837 (fine) |
| retail | 24 | 0.0000 | +0.1837 (fine) |

`device_sharing` actively favours `family` and `office` households over rings, by design: both
cluster types converge on up to 8 accounts on one device specifically to keep the device-only
baseline honest. This is the **identical structural blind spot RISK-001 (`ip_sharing`) and
RISK-004 (`instrument_sharing`) were**, now on the highest-weighted signal, undetected until a
benchmark with four distinct hard-negative types existed to reveal it -- because
`signal_sign_check` has only ever pooled all negatives together, never checked ring-vs-each-hard-
negative-type. By controller ruling, escalated to the human partner and documented rather than
patched: neither reweighting (no candidate in `A`-`E` targets `device_sharing` specifically) nor
widening the panel check itself (a methodology change to `riskmesh/integrity.py`, out of this
task's scope) was authorised as a side effect of a documentation task. Filed as `bugs.md`
RISK-005, open.

## The headline result: GraphSAGE ties Tier 1 on F1, beats it on expected loss

At each model's own cost-selected operating point (like-for-like, the exact pairing error above
made necessary to state explicitly): Tier 1 shipped at threshold 0.10, F1 0.5432, expected loss
92,263.55; Tier 3's `G2_two_layer` (Task 6's re-run winner, up from `G1_single_layer`) at threshold
0.03, F1 0.5412, expected loss 54,308.35. Verified directly against `experiments/weight_policy.json`
and `experiments/graphsage_policy.json` in this session. F1 is effectively tied (0.002 apart);
expected loss is **41.1% lower** ((92,263.55 - 54,308.35) / 92,263.55). This reverses the
"simplest model wins" conclusion that held on the pre-Task-3 benchmark, where Tier 3's single
feasible candidate (`G1_single_layer`) was worse than Tier 1 on both F1 (0.5000 vs 0.7778) and
expected loss (83,579.43 vs 74,595.13). Tier 2 (XGBoost) still has no feasible candidate at either
benchmark vintage, but by the **opposite mechanism**: originally `X1`-`X3` degenerated to constant
predictors on a ~30-row training split (`positives_below_max_negative == 0` for the wrong reason);
now, verified directly against `experiments/xgboost_policy.json` in this session, all four
candidates are refused for genuine over-separation (`DifficultyGateFailure` / `PanelGateFailure`,
`positives_below_max_negative` between 0.0435 and 0.2174 against the 0.45 floor) on a training set
124 components deep. `graphsage_protocol.md` and `xgboost_protocol.md` both present this as mixed,
not a win, in their own §8 sections (verified: GraphSAGE's write-up states outright "does not beat
Tier 1 on F1 ... this is not evidence GraphSAGE generalises better").

## Still open

RISK-005, D4, D5 (above); D2 and RISK-002's underlying feature-level mis-signs (resolved by weight,
not by fixing the feature -- see `bugs.md`); the `_build()` pipeline-setup block, now duplicated in
five places, deferred rather than extracted because Task 1's reviewer judged the risk of touching
`__main__.py`'s byte-for-byte reproducibility guarantee higher than the tidiness gain; nothing
tests `mockups/api.js` in the permanent suite, which is why Task 7's UI crash was caught by a
reviewer opening a browser rather than by any of the five green suites.

---

# Audit -- Tier 2 XGBoost and Tier 3 GraphSAGE, original protocol runs (pre-Task-6) . 2026-08-31 (backfilled 2026-09-05)

**Backfill notice.** Not written at the time either protocol closed, same lapse as every other
entry in this file before Task 9. Reconstructed 2026-09-05 from git history (`880ccfe` through
`fc4650c`, all 2026-08-31) and `xgboost_protocol.md` / `graphsage_protocol.md`'s own current text,
which documents both the original run described here and the Task 6 re-run described in the entry
above -- both are read directly from those files' §8 sections, not recalled. These records are
superseded by Task 6's re-run (see the entry above); they are reconstructed here because the
original run is itself a checkpoint the plan requires an entry for, and because its numbers are
the baseline the Task 6 re-run's "opposite mechanism" claim is measured against.

## What was built

`riskmesh/ml.py` (Tier 2, XGBoost) and `riskmesh/gnn.py` (Tier 3, hand-rolled GraphSAGE -- plain
torch tensor ops, no torch_geometric/dgl). Both follow `weight_search_protocol.md`'s exact
discipline: a fixed list of pre-declared candidates (four for XGBoost, three for GraphSAGE) rather
than a hyperparameter search, the identical three `costmodel.py` feasibility gates reused
unchanged, train-only fitting with a train+validation refit before any held-out read, and a
protocol document (`xgboost_protocol.md`, `242d078`'s `graphsage_protocol.md`) committed and
frozen before the implementation module existed. GraphSAGE's node features are deliberately
structural only (one-hot type + degree, normalised by the matching global cap) rather than the
linear scorer's 8 signals, so it answers a different question than XGBoost's over-same-evidence
comparison.

## Compared against the plan

Matches `implementation_plan.md`'s "Why abstention comes before XGBoost" reasoning, which named
the exact risk this stage tests for before it ran: "A gradient-boosted model has far more capacity
[than a linear score] to find [an easier benchmark], and it will find it preferentially." That
prediction held for XGBoost, in a different way than expected (see below).

## Results, both read from the frozen records

**XGBoost (`experiments/xgboost_policy.json` as originally frozen, commit `588d13b`).** All four
candidates refused, no held-out read taken, no winner named. `X1_shallow`/`X2_moderate`/
`X3_stumps` degenerated to a single constant prediction (`min_child_weight` never cleared on the
~30-row training split available at that benchmark size, confirmed against each fitted booster
directly) and tripped `positives_below_max_negative == 0` for a different reason than the gate was
built to catch; `X4_unregularised` genuinely over-separated, exactly as it was included to
demonstrate. Tier 1's F1 0.7778 / expected loss 74,595.13 (the Phase-12 RNG-fix numbers current at
that point) stood unchanged. `tests/test_ml.py` (4 checks): the gate fires against the deliberately
overfit `X4` candidate; `select_xgboost_model()` refuses a design view containing a test row;
`evaluate_frozen_ml_policy()` raises `MLPolicyNotFrozen` before the freeze file exists; refitting a
frozen configuration twice on identical data is bit-identical on the installed xgboost version.

**GraphSAGE (`experiments/graphsage_policy.json` as originally frozen, commit `ede6272`).** Run
against a freshly confirmed benchmark (`rm -rf out && python -m riskmesh` first). `G1_single_layer`
PASS (pbmn 0.75, hard-neg 8) -- feasible, the winner; `G2_two_layer` and `G3_unregularised` both
FAIL on over-separation (pbmn 0.00, hard-neg 0 for both). Unlike XGBoost, `G1` cleared the gate and
received its one permitted held-out read: F1 0.5000, expected loss 83,579.43 -- both worse than
Tier 1's frozen F1 0.7778 / 74,595.13. GraphSAGE did not beat Tier 1 at this benchmark vintage.
`tests/test_gnn.py` (4 checks) mirrors `test_ml.py`'s shape, with a fallback assertion that the
gate fires on *some* candidate if `G3_unregularised` ever stops tripping it by construction. Torch
2.13.0+cpu, `manual_seed` + `use_deterministic_algorithms` for reproducibility.

## Missing / orphaned

None found. Both dependency additions (`numpy`/`xgboost` for Tier 2, `torch` for Tier 3) are
confined to their own module; `python -m riskmesh` and `tests/test_riskmesh.py`'s zero-dependency
guarantee is unaffected, verified by the `requirements.txt` diff at each commit touching only the
new module's needs.

## Still open at this point in history

Neither model beat Tier 1. This is the state Task 6's re-run (see the entry above) overturned for
GraphSAGE and confirmed by a different mechanism for XGBoost.

---

# Audit -- Phases 10-12: hybrid ring type, D3 cost-model double-charge fix, RNG-isolation fix . 2026-08-31 (backfilled 2026-09-05)

**Backfill notice.** Not written at the time; reconstructed 2026-09-05 from git history (`912e4a2`,
`431d23e`, `c1d7672`, `821a687`, all 2026-08-31) and `deferred_decisions.md` D3's own closure text.
The pipeline was re-run as part of the Task 9 verification pass that wrote this entry
(`Config().fingerprint()` and a spot-read of `out/eval_report.json`, matching the current
`fdf4fc217347d36b` this file's newest entry above also cites), not re-run at the time each of these
three commits landed -- there is no way to retroactively close that gap for this specific
three-commit sequence the way the top entry of this file could for its own pair.

## What was built

**Phase 10 (`912e4a2`).** Two changes in one re-freeze cycle: (1) a hybrid pool-funded ring type
-- a tunable fraction of shared-device rings (`p_ring_instrument_funded`, tuned to 0.7) fund every
member through a small shared-instrument pool (`ring_instrument_pool_size`, tuned to 4) instead of
the flat 2-3-sharer partial overlap. This is RISK-004's own rejected experiment E6, restarted per
its closure note's explicit pointer, alongside a new always-on 8th signal
`instrument_pool_concentration`. (2) The D3 cost-model fix: `derive_costs()` no longer builds
`C_fp` with an embedded review-cost term, since the generic `(tp+fp)*C_review` term in
`expected_loss()` already charges one review per flagged component -- the old formula charged an
escalated false positive a review cost twice. `p_ring_instrument_funded=0.4` was tried first and
failed the difficulty gate (pbmn 0.3125 against >= 0.45); tuned up to 0.7 per the project's
"tune config, don't add realism" discipline until the panel passed (pbmn 0.5625, hard-neg 9).

**Phase 11 (`431d23e`).** Closed D1, D2 and D3 together: re-ran the weight search and abstention
protocol against the Phase 10 benchmark. The weight search selected `D_drop_flagged` (zeros
`instrument_sharing` and `merchant_concentration`) over `A_baseline`, tied on validation expected
loss (8,849.98) but winning the tie-break on a *sharper* `positives_below_max_negative` (0.625 vs
0.5625) -- folded back into `Config()._default_weights()`, closing D2 (`instrument_sharing` now
carries weight 0.00 as the shipped default, not a broken fallback -- the earlier zero-weight
attempt in RISK-004's own record had broken the panel; this one improved its margin). The abstention
re-run against the same benchmark selected `[0.14, 0.23)` -- non-degenerate in width but,
per `abstention_protocol.md`'s own later retrospective (§8, written at Task 6), one of the runs that
"widened `t_hi` modestly" rather than finding real work for Review to do, not the non-degenerate
result that entry credits to Task 6.

**Phase 12 (`c1d7672`, `821a687`).** An RNG-isolation bug: `_inject_rings`' Phase-10 branch drew
`sharers`/`share_rng` only inside the non-hybrid `else` branch, making the shared random stream's
consumption depend on `is_hybrid` -- the identical trap `experiment.py`'s own module docstring
warns about (the E3 mechanism). Changing `p_ring_instrument_funded` therefore reshuffled unrelated
downstream randomness (family details, background traffic) instead of isolating the change to
which rings are hybrid. Fixed by drawing `sharers`/`share_rng` unconditionally every ring and
giving the hybrid-vs-non-hybrid signup-day draw its own dedicated per-ring `Random` (`randint`'s
rejection sampling consumes a variable number of underlying words depending on the range argument,
so matching call counts alone does not isolate two branches with different bounds). Verified: two
runs differing only in `p_ring_instrument_funded` now produce byte-identical family membership,
first account id, and total transaction count. This changes generator output without moving the
config fingerprint (the fingerprint hashes config fields, not generator code), so every frozen
number downstream was stale; `c1d7672` re-ran both protocols end to end against the corrected
benchmark (weight search: `A_baseline` wins outright in one pass, threshold 0.18, validation loss
4,000.00, held-out 74,595.13; abstention: the free search now selects a **degenerate** band,
`t_lo = t_hi = 0.18`, identical to the binary policy -- the validation split has neither a missed
positive nor a false positive for Review to act on), and `821a687` re-derived every other stale
number field-by-field against a fresh `out/` rather than hand-patching, including a
"Held-out-F1-copied-into-Hard-neg-F1" bug in several `implementation_plan.md` table rows this same
pass caught.

## Compared against the plan

Matches `implementation_plan.md`'s Phase 10-11 (renamed 10-12 after the RNG fix) sections and
`deferred_decisions.md` D3's closure note. `bugs.md` RISK-004's forward note is the direct pointer
this phase followed ("If Tier 1 or Tier 2 adds a funding-network ring type... this signal should be
revisited from E6's design").

## Gaps found by this backfill

None beyond the absent audit entry itself, which this entry closes. The RNG-isolation bug was
already found and fixed within this same commit sequence (`c1d7672`), not left for this backfill
to discover -- it is recorded here as a checkpoint event, not a new finding.

## Missing / orphaned

None. `run_e6`'s design (accounts-per-instrument, funding pool) is exactly what Phase 10's hybrid
mechanism implements; nothing from the E6 record was left unused or duplicated.

---

# Audit -- abstention band frozen, non-degenerate Review policy, single held-out read . 2026-08-26 (backfilled 2026-09-05)

**Backfill notice.** Not written at the time; reconstructed 2026-09-05 from git history (`8f58520`)
and `abstention_protocol.md`'s own §8/§8b sections. This entry's numbers describe the band as
originally frozen on 2026-08-26, against the same Tier 1 benchmark the top-of-file
weight-search entry (`96ae30f`..`d819b56`, 2026-08-25) was frozen against -- they are superseded by
Task 6's re-freeze, described in this file's newest entry above, the same way that entry's own
weight-search numbers are.

## What was built

`riskmesh/abstention.py`: a three-way allow/review/escalate policy layered on top of the already-
frozen `A_baseline` scorer. The scorer, its seven weights, and the binary threshold (0.23 at the
time) are left untouched -- F1 0.8000 / expected loss 9,392.92 stand exactly as the weight-search
entry above recorded them. Mechanism: two thresholds (`t_lo`, `t_hi`), both freely searched over
the full grid rather than pinning 0.23 as the Allow boundary -- the free search landed on 0.23 on
its own, a result rather than a built-in constraint. `MAX_REVIEW_RATE = 0.25` declared before any
band was scored and enforced structurally by `ReviewBandGateFailure`, mirroring
`costmodel.py`'s own discipline exactly. `evaluate_frozen_abstention_policy()` raises
`AbstentionPolicyNotFrozen` unless the exact frozen band is the one being read -- same
freeze-then-single-read shape as `select_weights()`.

## Compared against the plan

Selected band: `t_lo 0.23`, `t_hi 0.33`. Matches `implementation_plan.md`'s "Plan: argue abstention
before XGBoost from the held-out evidence" (commit `d819b56`), which frames this stage's purpose
correctly: establishing a three-way policy and its cost before handing a higher-capacity model
(XGBoost) more room to find an easier benchmark, per `bugs.md` L2's own warning.

## Gaps found by this backfill

None found in the technical record. The one gap is procedural -- no audit entry existed for this
stage until now, which is what this entry closes.

## Missing / orphaned

None. The record is superseded, twice over before Task 6, but not orphaned -- it is provenance for
the abstention mechanism's first real run, kept the same way E1-E6 are kept for the weight search.
The supersession chain, stated in full since no single downstream doc states all four points
together: this run (`t_lo 0.23`/`t_hi 0.33`, 2026-08-26) -> Phase 10/11's re-run against the hybrid-
ring benchmark (`t_lo 0.14`/`t_hi 0.23`, see the Phases 10-12 entry above) -> Phase 12's re-run
after the RNG-isolation fix, which collapsed to the degenerate `t_lo = t_hi = 0.18` (identical to
the binary policy, same entry above) -> Task 6's re-run, `t_lo 0.10`/`t_hi 0.20`, which
`abstention_protocol.md` credits as "the first run in this project's history where the free search
does not collapse to the binary threshold" -- a claim made against the runs its own current text
still names (Phase 10/11 and Phase 12), not against this original 2026-08-26 run, whose numbers had
already been overwritten twice by the time that sentence was written and are not part of what it is
comparing against.

---

# Audit -- weight-search protocol run, A_baseline retained, held-out read taken . 2026-08-25 (backfilled 2026-08-26)

**Backfill notice.** This entry and the one below it (RISK-004 closure) were not
written at the time of their ritual close, breaking the per-phase discipline
`implementation_plan.md` sets out. They are reconstructed on 2026-08-26 from git
history (commits `96ae30f` through `d819b56`) and the frozen records in
`experiments/` and `out/`, not from a contemporaneous `rm -rf out && python -m
riskmesh` run the way the entries below this pair were. Read them as a
retrospective comparison, not a same-day one — the risk that mitigates against
is a live check catching something a backfill reading of committed files can
miss, and the pipeline was re-run and re-tested as part of the same cleanup pass
that wrote this entry (`python -m riskmesh`, `python tests/test_riskmesh.py`,
`pyright`) to close that gap as far as retroactively possible.

## What was built

`riskmesh/costmodel.py` (460 lines): `PanelGateFailure` / `DifficultyGateFailure`
/ `PolicyNotFrozen` exception types, `derive_costs()`, `expected_loss()`,
`panel_verdict()`, `gated_expected_loss()`, the five named policy functions
(`policy_a_baseline` through `policy_e_drop_temporal`), `select_weights()`,
`evaluate_frozen_policy()`, `freeze_policy()`. `weight_search_protocol.md`
frozen before `select_weights()` existed (commit `96ae30f`), matching the
plan's "rules are written down while the answer is still unknown" discipline
used for every prior experiment. `experiments/weight_policy.json` (and its
`out/` copy) is the frozen record.

## Compared against the plan

`implementation_plan.md`'s "Tier 1 — cost model and weight selection (DONE)"
section documents this stage in full and matches what is in `costmodel.py` and
`weight_policy.json`: five candidates, three structural gates, A_baseline
retained, the single held-out read (F1 0.8000, expected loss 9,392.92 at
threshold 0.23). `deferred_decisions.md` D1 and D2 were updated with the
coupling note this stage surfaced (zeroing `instrument_sharing` pushes
`temporal_burst` to 0.3247) — present and correct.

## Gaps found by this backfill, now fixed as part of the same cleanup

- `weight_search_protocol.md`'s status line read "the held-out split has **not**
  been read; step 5 is still pending review" while §8 of the same file
  contained the completed read. Corrected to state the protocol is run and
  closed.
- The same stale claim had leaked into `tests/test_riskmesh.py`'s own console
  output (`"weight-search protocol (frozen, not run)"`, printed immediately
  before the test that exercises the gate) and into README.md's working-files
  list (`weight_search_protocol.md (frozen, not yet run)`). Both corrected.
- `riskmesh/config.py` carried two pairs of duplicate field declarations
  (`ring_instrument_pool_size`, `instrument_sharing_accounts_per_card`) left
  over from a copy-paste in the E6 commit (`934929e`). Harmless — Python
  dataclasses silently keep the last declaration, confirmed by re-hashing
  before and after the fix (`7c1e4fb2b329796c` unchanged) — but noise a future
  reader would have had to work through. Deduplicated.
- No audit entry existed for this stage or for RISK-004's closure, which is
  the gap this entry and the next one close.

## Missing / orphaned

None found. `out/weight_policy.json` and `experiments/weight_policy.json` are
identical copies (the latter is the durable one, `out/` being gitignored),
consistent with the pattern already established for the E1–E6 records.

---

# Audit -- RISK-004 closed as rejected-as-a-production-signal . 2026-08-25 (backfilled 2026-08-26)

See the backfill notice above; it applies to this entry too.

## What was built

Three pre-registered experiments (`run_e4`, `run_e5`, `run_e6` in
`riskmesh/experiment.py`, lines 469, 810, 974) plus a pre-declared zero-weight
fallback, each frozen to `experiments/experiment_e{4,5,6}.json` before its
held-out read. `bugs.md` RISK-004 carries the full closure statement and scope
caveat; `deferred_decisions.md` D2 carries the forward-looking decision the
cost-model stage owns; `bugs.md` L1 (size-based normalisation) was filed as a
standing lesson out of E5, separate from the RISK-004 direction failure it was
found inside.

## Compared against the plan

Matches `implementation_plan.md`'s "Tier 1 remaining" item 7, which already
correctly points a future funding-network ring type at "`experiment_e6.json`"
as the restart point rather than treating E6 as dead work. `experiments/README.md`'s
table of all six frozen experiments (E1–E6) is present and its per-row
outcomes match the commit messages and `bugs.md` verbatim.

## Gaps found by this backfill

None in the technical record — RISK-004's closure statement in `bugs.md` is
unusually thorough (it pre-empts the most likely mis-reading of the result,
that "instrument sharing is a useless signal," and explicitly forecloses it).
The only gap was procedural: this audit entry itself not having been written
at close time, and `implementation_plan.md`'s item 6 (RISK-002, a different but
adjacent signal) conflating a ring-vs-family delta with a ring-vs-all-negatives
delta — fixed in this same cleanup pass, in `implementation_plan.md` and
`bugs.md` RISK-002.

## Missing / orphaned

None. `run_e4`, `run_e5`, `run_e6` and their four rejected `Config` fields
(`ring_instrument_share`, `instrument_sharing_component_relative`,
`ring_instrument_pool_size`, `instrument_sharing_accounts_per_card`) are kept
deliberately, per the plan's own "rejected-alternative provenance, not dead
code" framing for E4 — not orphans, evidence.

---

# Audit -- RISK-003 closed, E2 adopted, generator frozen . 2026-08-25

Newest audit first. The RISK-001 audit follows below, unchanged.

**Every figure here was read from `out/` after `rm -rf out` and a fresh
`python -m riskmesh`.** Config fingerprint `b7b069226b2299c7`, seed 20260824,
Python 3.12.10. `python tests/test_riskmesh.py` 19/19; pyright 0 errors. Both
were run *before* tagging, not after.

## What changed

One line of `config.py`: `family_coburst_shared_merchant` True -> False. A
household's co-burst now lands on each member's own merchant instead of all
members converging on one. Nothing else moved -- not the ring injector, not a
weight, not a signal definition.

## Reproduction check against the frozen E2 record

The instruction was not to assume the experiment and the default-config run are
equivalent just because the mechanism is the same. They were compared directly
against `out/experiment_e2.json`:

| signal | ring | family | background | delta | E2 delta |
|---|---|---|---|---|---|
| device_sharing | 0.4716 | 0.3580 | 0.0835 | +0.1136 | +0.1136 |
| temporal_burst | 0.2969 | 0.1016 | 0.0034 | **+0.1953** | **+0.1953** |
| instrument_sharing | 0.2031 | 0.2969 | 0.0372 | -0.0938 | -0.0938 |
| failure_refund_rate | 0.2751 | 0.1369 | 0.0051 | +0.1383 | +0.1383 |
| ip_sharing | 0.0000 | 0.5625 | 0.0000 | -0.5625 | -0.5625 |
| account_newness | 0.9069 | 0.0250 | 0.1403 | +0.8819 | +0.8819 |
| merchant_concentration | 0.2483 | 0.2380 | 0.3275 | +0.0103 | +0.0103 |

All seven identical to full float precision. Panel figures also match:
positives-below-max-negative 0.5625, hard negatives in the positive range 4,
shared-device baseline F1 0.7442. Held out at frozen threshold 0.23: precision
0.6667, recall 1.000, F1 0.800, FPR 0.1739, ring recovery 8/8 -- E2's recorded
numbers exactly.

**One discrepancy, found and explained rather than waved through.** The config
fingerprint is `b7b069226b2299c7`, not E2's recorded `381948e3f5dc84cc`. Cause:
`family_merchant_overlap` and `family_merchant_pool_size` were added to `Config`
*after* the E2 run, for E3, and `fingerprint()` hashes every field. Hashing
today's config with those two fields removed returns `381948e3f5dc84cc` exactly,
so the delta is fully accounted for and no generator behaviour changed. Both
fields keep their inert defaults (0.0 and 4).

## The full config-fingerprint chain, verified by re-hashing at every step

The transition above is one hop in a longer chain that runs through the rest of
RISK-004. Recorded here in full, once, so no later reader has to re-derive it.
Every hop was produced the same way: an experiment adds a `Config` field for its
own inert default, and `fingerprint()` hashes every field
(`json.dumps(asdict(self), ...)`), so a schema addition moves the hash even when
every value that matters is unchanged. Verified directly — not inferred — by
taking the current `Config()`, deleting each named field from its `asdict()`
dict, and re-hashing:

| fingerprint | recorded where | config state | fields removed to reach the previous hash |
|---|---|---|---|
| `381948e3f5dc84cc` | `experiments/experiment_e2.json` | E2 experiment run (commit `dcc0a25`) | — (earliest of the four) |
| `b7b069226b2299c7` | this file, above; `bugs.md` RISK-003 | E2 adopted as default (commit `af8a769`) | `family_merchant_overlap`, `family_merchant_pool_size` (added for E3, commit `982345a`) |
| `6ebb043b3c1954b1` | `experiments/ablation_temporal_burst.json` | Tier 1 ablation gate (commit `e93033c`) | `ring_instrument_share` (added for E4, same commit) |
| `7c1e4fb2b329796c` | `out/integrity_report.json`, `experiments/weight_policy.json` (current) | after E5 + E6 (commits `d62f15d`, `934929e`) | `instrument_sharing_component_relative` (E5), `ring_instrument_pool_size`, `instrument_sharing_accounts_per_card` (E6) |

Re-hash check, run against the current `Config()`:

```
current fingerprint                    7c1e4fb2b329796c
minus E5/E6 fields                  -> 6ebb043b3c1954b1  (matches the ablation record)
minus E4 field too                  -> b7b069226b2299c7  (matches E2-adoption)
minus E3 fields too                 -> 381948e3f5dc84cc  (matches the E2 experiment record)
```

All four match exactly. No generator or scorer behaviour changed at any of these
four hops — every field involved keeps an inert default (`0.0`, `False`, or a
value equal to the prior behaviour) until the experiment that owns it is
adopted. E4 (`ring_instrument_share`), E5
(`instrument_sharing_component_relative`) and E6 (`ring_instrument_pool_size`,
`instrument_sharing_accounts_per_card`) were all rejected — see `bugs.md`
RISK-004 — so their fields sit at inert defaults today and always have.

## Transaction count moved 5968 -> 5962

Expected, not a regression. With `shared_merchant=False`, `_add_burst` draws an
extra `rng.choice(acct.merchants)` per burst transaction, which shifts the shared
RNG stream downstream. This is the same denominator effect the E2 record already
documented for `failure_refund_rate` (-0.0011) and `merchant_concentration`
(-0.0022), and it is inherent to the mechanism rather than a leak: the change
*is* a change to what the generator draws.

## Rejected alternatives kept

`experiments/` now holds durable copies of all three frozen records with an index
of why each was accepted or rejected. `out/` is gitignored, so the E1 and E3
records would otherwise have been one `git clean` from gone; they are provenance
for why the adopted design looks the way it does, not dead work.

## Still open

RISK-002 (`merchant_concentration` mis-signed, FLAG-level, weight 0.0889) and
RISK-004 (`instrument_sharing` scores families 0.2969 above rings 0.2031 at
weight 0.1444). Together they are ~0.23 of the scorer's weight still not doing
its intended job -- down from the ~0.42 before RISK-001 and RISK-003 closed. The
Tier 1 ablation gate (temporal_burst in vs out, measured on ring-vs-family) is
still unrun and still gates any pitch claim about the signal.

---

# Audit — RISK-001 closed (Tier 1 entry) · 2026-08-25

> Compare what is actually built against `implementation_plan.md`. What is
> missing? What was built wrong? Are there any orphaned files?

## Built vs. plan — all 10 phases

| Phase | Deliverable | Status |
|---|---|---|
| 0 | package, requirements, gitignore, guardrail files | done |
| 1 | `config.py` — frozen Config, fingerprint | done |
| 2 | `generate.py` — entities, correlated normal traffic | done |
| 3 | `generate.py` — ring + family injectors, period confinement | done |
| 4 | `graph.py` — 3 hygiene rules, union-find | done |
| 5 | `score.py` — 7 signals, raw + normalised + detail | done |
| 6 | `split.py` — chronological ring-level, dual-path | done |
| 7 | `integrity.py` — report + non-triviality panel | done |
| 8 | `evaluate.py` + `__main__.py` — freeze, metrics | done |
| 9 | `tests/test_riskmesh.py` (18/18), `README.md` | done |

`python -m riskmesh` runs end to end; `python tests/test_riskmesh.py` passes
19/19; pyright reports 0 errors across the package.

**Every figure below was read directly from the regenerated artifacts in `out/`
after `rm -rf out` and a fresh run, not recalled from a prior run.** Config
fingerprint `7ea3c87d216e5d47`, seed 20260824, Python 3.12.10.

- 5968 transactions, 789 accounts, 975 devices, 902 IPs, 823 instruments, 40 merchants
- 24 rings, 24 family clusters
- 100 candidate components, 402 singletons dropped, largest 9 accounts (1.14%, bound 15%)
- capped nodes {'device_id': 0, 'ip_id': 20, 'instrument_id': 0}; NAT IP reuse 55-89 accounts each
- transactions per split {'train': 2212, 'validation': 1600, 'test': 2156}
- class balance (positive/negative): train 8/30, validation 8/23, test 8/23
- panel verdict **PASS**; positives below max negative 0.9375; hard negatives inside the
  positive range 8; shared-device baseline F1 0.7442
- flagged signals {'ip_concentration': 0.9697}; inverted signals ['account_newness', 'ip_concentration', 'merchant_concentration']
- held out at frozen threshold 0.27: precision 0.5333, recall 1.0, F1 0.6957,
  FPR 0.3043, ring recovery 8/8

## Deviations from the plan

1. **`n_rings` 12 → 24, `n_families` 15 → 24, `n_accounts` 600 → 520.** The plan's
   12 rings gave 4 positive components per split, quantising test precision to
   quarters. Too coarse to report honestly. Transaction count rose to ~5.6k,
   slightly over the plan's 5k target, which the plan called approximate.

2. **`family_size_max` 5 → 8.** With 24 rings the shared-device-only baseline hit
   F1 0.857, breaching its 0.85 bound — negatives topped out at 5 accounts per
   device while rings reached 9, so "many accounts on one device" became almost
   sufficient on its own. Large households fixed it (now 0.744). This was found
   by the panel, not by inspection.

3. **`max_instrument_degree` added, then raised to 9.** Not in the plan (which
   named IP and device caps only) but `graph.py` links on instruments too. Raised
   above `family_size_max` so a genuine family card is never miscategorised as
   common infrastructure.

4. **`account_age_days` added to `Txn`.** The `account_newness` signal needed
   tenure, which existed only on the generator's internal `Account`. Account age
   at authorisation is platform metadata, not ground truth.

5. **Four family/background knobs promoted from hardcoded values to `Config`**
   (`family_coburst_participation`, `family_coburst_window_multiplier`,
   `family_signup_min/max_days`, `bg_active_days_min/max`). The plan requires
   tuning by config change rather than code change; two of these were literals
   inside `generate.py`, which would have forced a code edit.

6. **Phases 7 and 8 were built in the order 8-then-7.** `integrity.py` needs the
   ground-truth rule and the F1 helpers, which the plan places in `evaluate.py`.
   Writing 7 first would have meant stubbing them twice.

## RISK-001 resolution (first Tier 1 task)

Tagged `tier0-baseline` at 342b1bb before any change.

**Investigated before changing anything.** Two separable causes, both measured on
train+validation only:

1. *Real structural difference.* `_inject_rings` never touches `home_ip` — max
   accounts on one non-common IP is exactly 1.00 for all 24 ring components
   against 4.94 for families. Tier 0 places no ring information in the IP
   dimension. Not the `ring_shared_device_share` mechanism, which governs devices
   only.
2. *Definitional defect.* The signal measured transaction share, not accounts
   sharing an IP, unlike its device and instrument siblings — making it a
   back-door ring detector keyed on the absence of a household (rings 0.162,
   background 0.462, families 0.701 = p_home_ip). Not a size proxy: the gap is
   flat at every size 4-8 and pure 1/size reaches only F1 0.727 vs 0.970.

**Chose redefinition plus zero weight**, rejecting inversion (it would encode
"not sharing infrastructure is suspicious", a fit to this generator config that
flips when Tier 1 adds shared-IP rings) and rejecting outright removal (the
redefinition is correct and Tier 1 will make it discriminative).

**Comparison against tier0-baseline** — identical data, scorer only; the
threshold was re-frozen on validation before test was read:

| | tier0-baseline | RISK-001 fixed |
|---|---|---|
| positives below max negative | 0.9375 | 0.9375 |
| shared-device-only baseline F1 | 0.7442 | 0.7442 |
| hard negatives in positive range | 8 | 5 |
| test precision | 0.5333 | 0.6154 |
| test F1 | 0.6957 | 0.7619 |
| test FPR | 0.3043 | 0.2174 |
| test recall / ring recovery | 1.0 / 8-8 | 1.0 / 8-8 |
| panel verdict | PASS | PASS |

**New standing check.** `signal_sign_check` computes each signal's direction on
the *normalised* values that enter the score, which is the only view that
separates a correct inversion (`account_newness`, +0.801) from a mis-signed one.
Added as a FLAG-level row, `no_weighted_signal_mis_signed`. It immediately
surfaced **RISK-002** (`merchant_concentration`, delta -0.051, contribution
-0.0046 of a +0.2652 total), filed and deferred rather than fixed, so this
change's before/after stays attributable to one cause.

## Post-review corrections

7. **`single_signal_f1` swept only one threshold direction.** It tested
   `value >= t` only, so the three signals that separate on LOW values were
   reported at ~0.38 when they actually reach 0.9697 (`ip_concentration`),
   0.9412 (`account_newness`) and 0.4923 (`merchant_concentration`). The
   "no single signal separates perfectly" guard was therefore blind to perfect
   separation in the inverted direction -- the exact case it exists to catch.
   Fixed to take the max over both directions; `flagged_signals` now correctly
   names `ip_concentration`. Regression test 06b covers it with an
   inverse-direction fixture, and additionally asserts that a `>=`-only sweep
   would fail on that fixture, so the test cannot silently stop discriminating.

8. **I fabricated figures in an earlier version of this file.** "5644
   transactions, 806 accounts" was written from memory after a truncated run
   output; the real values are above. The README's NAT reuse range (stated as
   40-70, actually 55-89) was wrong the same way. Both corrected, and every
   number in this file and the README is now read from the JSON artifacts.

9. **RISK-001 filed and deferred.** `ip_concentration` carries +0.10 weight
   while separating in the inverted direction. Left untouched during Tier 0.

## Process notes

- **One error worth recording:** the first generator-tuning sweep printed test F1
  alongside the panel results. Selecting generator parameters on a test statistic
  is precisely what the PRD forbids. The sweep was redone against the panel and
  the validation threshold only, and the selection rule is now written into
  `config.py` next to the bounds.
- **One misread:** `positives_below_max_negative` at 0.94 was initially taken as
  "the data is unsolvable". It is driven by the single highest-scoring negative,
  so it means one very ring-like family — a hard negative doing its job.
  Validation F1 of 0.89 confirms the data separates. The bound is a floor, not a
  target.

## Missing

Nothing from the Tier 0 slice. Out of scope by design: SQLite, FastAPI, React
console, LLM layer, XGBoost, GNN, cost model, ablations, confidence intervals,
the full baseline suite, and the remaining ring/hard-negative types.

## Orphaned files

None. Every `Config` field has a reader — verified by grepping each field name
against the package. `out/` holds only the six generated artifacts and is
gitignored. `task_today.md` was deleted at each phase close, as intended.

## Open bugs

None. `bugs.md` holds one closed entry (B1, background components all landing in
the train split), fixed and covered by a strengthened `testing.md` row.

## Honest reading of the result

Recall 1.000 with precision 0.533 is not a good detector; it is a working
benchmark with a threshold picked by max-F1 on validation, which favours recall.
Seven false positives out of 23 test negatives is the false-positive pressure the
hard negatives were built to create. Tier 1's expected-cost thresholding is what
turns that into a defensible operating point — that is the next phase's job, and
reporting the number honestly now is the point of Tier 0.
