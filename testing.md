# RiskMesh — testing checklist

Every row here must pass before a phase is considered done. Rows marked
**scripted** are automated in `tests/test_riskmesh.py`; rows marked **manual**
are read by eye from `out/integrity_report.json`.

Run the scripted rows with:

```
python tests/test_riskmesh.py
```

Status: `[ ]` not yet verified · `[x]` passing · `[!]` failing (open entry in `bugs.md`)

---

## Phase 1 — Config and seed

- [x] **scripted** — scorer weights sum to 1.0 within 1e-9
- [x] **scripted** — `Config.fingerprint()` returns the same value on two calls
- [x] **scripted** — `Config` is frozen: assigning to a field raises
      `FrozenInstanceError`

## Phase 2 — Entities and normal traffic

- [x] **scripted** — transaction count is `cfg.target_txns` ±10% (19,300
      ±10%, actual 19,310) *(test 01b, replaces a self-check that used to
      live only in `generate.py`'s own `__main__` block and was never run by
      this suite)*
- [x] **scripted** — accounts-per-device is mostly 1, with a thin tail
- [x] **scripted** — every carrier-NAT IP is used by far more accounts than
      `max_ip_degree` (margin `nat_common_infra_margin`x), so hygiene must cap it
- [x] **manual** — reuse histograms in the integrity report look plausible, not
      uniform

## Phase 3 — Ring and family injectors

- [x] **scripted** — every ring's and cluster's coordinated activity falls inside
      exactly one period
- [x] **scripted** — `transactions.csv` header contains no ring/cluster/label
      column *(test 2, no label leakage)*
- [x] **scripted** — `labels.csv` exists and carries account/ring/cluster/period
- [x] **scripted** — every hard-negative cluster shares ≥1 attribute type with
      at least one ring pattern *(test 6, hard negatives are hard — Task 4
      generalised the message from "family(ies)" to "cluster(s)" since
      `has_family` now covers all four cluster types, not only family; the
      assertion itself, `shared & ring_attrs`, was already correct both
      before and after)*
- [x] **scripted** — all five ring types (`device`, `hybrid`, `instrument`,
      `ip`, `refund`) appear in `labels.csv`, and every ring is one type
      inside exactly one split *(test 03b, added Task 3)*
- [x] **scripted** — every one of the five ring types yields ≥1 positive
      design candidate, checked per type so one invisible type cannot hide
      behind the other four's counts *(test 03c, added Task 3; this is the
      check that would have caught Task 3's own refund-abuse structural-edge
      bug — see `bugs.md`/Global Constraint G6b)*
- [x] **scripted** — all four hard-negative cluster types (`family`,
      `hostel`, `office`, `retail`) appear in `labels.csv`, and every cluster
      is one type inside exactly one split *(test 03d, added Task 4)*
- [x] **scripted** — every one of the four cluster types yields ≥1 candidate
      component (any split — clusters are never "positive," so this checks
      component formation, not positivity), per type *(test 03e, added
      Task 4; the retail-cluster analogue of 03c, added after review found
      retail clusters were structurally invisible under the same G6b defect)*
- [x] **scripted** — a `<=` sweep finds signals a `>=`-only sweep would hide
      as useless (F1 1.0 inverted vs 0.667 one-directional); reports which
      signals currently invert on raw values *(test 06b — pre-existing,
      previously missing a testing.md row; live inverted signals on the
      current benchmark: `account_newness`, `device_sharing`, `ip_sharing`,
      `merchant_concentration`, per RAW-value direction only — see
      `out/integrity_report.json`'s `inverted_signals_note` for why a raw
      inversion is not by itself a fault)*

## Phase 4 — Graph and component hygiene

- [x] **scripted** — largest component holds <15% of accounts *(test 5)*
- [x] **scripted** — every carrier-NAT IP is flagged common infrastructure
      *(test 5)*
- [x] **scripted** — capped nodes are recorded for the integrity report
- [x] **manual** — component-size distribution has no unexplained giant component

## Phase 5 — Deterministic scorer

- [x] **scripted** — weights sum to 1.0 and score lands in [0, 1]
- [x] **scripted** — every signal returns `raw`, `normalized`, `weight`,
      `contribution`, `detail`
- [x] **scripted** — scoring the same component twice gives an identical result
- [x] **scripted** — `score_component()` accepts no label argument *(test 2;
      also enforced statically by pyright)*

## Phase 6 — Chronological ring-level split

- [x] **scripted** — `active_period == median_timestamp_period` for every labeled
      component *(test 4)*
- [x] **scripted** — no ring or cluster spans two splits *(test 3)*
- [x] **scripted** — all three splits contain at least one ring
- [x] **manual** — split boundaries in the report are chronological, train → val →
      test

## Phase 7 — Integrity report and non-triviality

Bounds come from `config.py`; the panel is computed on train+val only.

- [x] **scripted** — positive and negative score distributions overlap *(test 7)*
- [x] **scripted** — ≥ `min_positive_below_max_negative_fraction` (0.20) of
      positives score below the highest-scoring negative *(test 8)*
- [x] **scripted** — ≥1 hard-negative family component lands inside the positive
      score range *(test 9)*
- [x] **scripted** — no single raw signal reaches max F1 == 1.0 *(test 10, hard
      failure)*
- [x] **manual** — any signal with max F1 in [0.95, 1.0) appears under
      `flagged_signals` and has been looked at *(test 10, flag only)*
- [x] **scripted** — shared-device-only baseline F1 <
      `max_shared_device_baseline_f1` (0.85) *(test 11)*
- [x] **manual** — per-feature positive/negative ranges visibly overlap
- [x] **scripted** — no weighted signal is mis-signed, i.e. no signal with
      weight > 0 has a normalised mean lower on positives than negatives
      *(test 19; FLAG-level, not FAIL. As of Phase 11's fold-back,
      `merchant_concentration` carries weight 0.00, so it is no longer in
      the weight > 0 population this check inspects; `flagged_signals` on
      the current benchmark is `none` — see `out/integrity_report.json`.
      `merchant_concentration` is still mis-signed as a *feature* (RISK-002,
      RESOLVED BY WEIGHT in `bugs.md` — the weight was zeroed as a side
      effect of a different objective, the feature itself was never fixed),
      which is why this row is worded as "no weighted signal", not "no
      signal")*

## Phase 8 — Evaluation runner

- [x] **scripted** — validation-selected threshold is persisted to
      `out/threshold.json` *(test 12)*
- [x] **scripted** — test evaluation reads that frozen value back rather than
      recomputing it *(test 13)*
- [x] **scripted** — threshold in `eval_report.json` equals the validation
      threshold *(test 14)*
- [x] **scripted** — `TP + FP + TN + FN == len(test_components)` *(test 15)*
- [x] **scripted** — test split contains ≥1 positive ring component *(test 16)*
- [x] **scripted** — test split contains ≥1 negative component, and every
      split contains ≥1 *unlabelled* background component *(test 17; strengthened
      after bugs.md B1 — the original row passed on families alone)*
- [x] **manual** — `eval_report.json` has both `primary` (component) and
      `secondary` (account) blocks

## Phase 9 — Reproducibility and docs

- [x] **scripted** — two runs at the same seed produce byte-identical
      `transactions.csv` *(test 1)*
- [x] **scripted** — two runs at the same seed reproduce every output file
      *(test 18)*
- [x] **manual** — `python -m riskmesh` works from a clean clone with no install
      step
- [x] **manual** — README documents the run command, the outputs, the scorer
      weights, the three hygiene rules, and the Tier 0 ground-truth rule limit

## Phase 10 — Hybrid pool-funded rings, the 8th signal, the D3 fix

- [x] **manual** — a configurable fraction of rings (`p_ring_instrument_funded`)
      are pool-funded through a shared instrument pool and draw signup age from
      a wide range, alongside the untouched majority mechanism
- [x] **scripted** — `instrument_pool_concentration` returns `raw`, `normalized`,
      `weight`, `contribution`, `detail` like every other signal *(test 07-11
      non-triviality panel already exercises all `SIGNALS`)*
- [x] **scripted** — the non-triviality panel still PASSes on train+validation
      with the new signal and ring mechanism active *(test 07-11)*
- [x] **manual** — `deferred_decisions.md` D3 resolved: `derive_costs()`'s
      `C_fp` no longer embeds a review cost; `(tp+fp)*C_review` is the only
      review charge

## Phase 11 — Weight search and abstention band re-frozen against Phase 10

**Superseded by Phase 12 below.** The numbers in this section were current
when Phase 11 closed; Phase 12 fixed an RNG-isolation bug in the same
generator mechanism (`riskmesh/generate.py`) that changed actual output
without moving the config fingerprint, so `weight_search_protocol.md` and
`abstention_protocol.md` were re-run again and every figure below is now
historical, not a description of what `tests/test_riskmesh.py` currently
asserts. Kept for the phase-by-phase record; see Phase 12 for current
numbers.

- [x] **scripted** — the weight-gate test refuses `B_equal` and (under the new
      weight vector) `E_drop_temporal`, and confirms `A_baseline` and
      `D_drop_flagged` both remain feasible and tie *(test 19)*
- [x] **manual** — `weight_search_protocol.md` re-run end to end: `D_drop_flagged`
      won on the first pass, was folded into `Config()._default_weights()` per
      the protocol's own re-freeze rule, and the second pass reached a fixed
      point in one iteration
- [x] **scripted** — `experiments/weight_policy.json` carries the current
      config fingerprint, and the pipeline's copy into `out/` matches it --
      caught not by test 18 (`_copy_frozen_record` is a byte copy, so
      byte-for-byte reproducibility cannot detect a stale-but-matching source
      file by construction) but by config-fingerprint agreement checked at
      `Artifacts` load time (`test_api.py` test 01/02), plus the
      weight-search and abstention regression tests that recompute a frozen
      figure live against the current code and data (test 19, test 20)
- [x] **scripted** — the binary/three-way collapse at `t_lo = t_hi` reproduces
      the current frozen expected loss (8,849.98 at threshold 0.14) exactly
      *(test 20)*
- [x] **manual** — `abstention_protocol.md` re-run end to end: band
      `t_lo=0.14, t_hi=0.23`, held-out expected loss 6,808.33 against the
      binary policy's 8,041.65, a 15.3% reduction with one escalated false
      positive (not zero, unlike the original run)
- [x] **manual** — `implementation_plan.md` "Phase 10-12" (the section this
      row originally called "Phase 10-11" before Phase 12 merged into the
      same heading — corrected here since the old name no longer resolves to
      any heading in that file) reports the account-age-confound target
      honestly: `transaction_level` no longer reaches held-out F1 1.0000
      (now 0.7143 at the time this row was written), and the shipped
      `ring_score` (0.8750) beats it outright
- [x] **manual** — every document quoting a weight-search or abstention number
      (`weight_search_protocol.md`, `abstention_protocol.md`,
      `deferred_decisions.md`, `bugs.md` RISK-004, `implementation_plan.md`,
      `README.md`) updated to the re-frozen figures

## Phase 12 — RNG-isolation fix in `_inject_rings`, second re-freeze

**Superseded by the Tasks 1-7 benchmark rebuild below.** The numbers in this
section (fingerprint `c3ee14627c2c2ce2`, `A_baseline` at threshold 0.18,
held-out expected loss 74,595.13) were current when Phase 12 closed. Tasks
3-4 then raised the population and added four ring types plus three
hard-negative types (fingerprint now `fdf4fc217347d36b`), and Task 6 re-ran
all four freeze protocols against the new benchmark. Every figure below is
historical, not a description of what the current suites assert. See
"Tasks 1-7" below for current numbers and rows.

A final whole-branch review found that Phase 10's instrument-mechanism
if/else in `_inject_rings` let the main RNG stream's consumption depend on
`is_hybrid`, a data-dependent branch — the exact trap
`riskmesh/experiment.py`'s module docstring names, learned the hard way in
E3. Fixed by drawing the `sharers`/`share_rng` values unconditionally, every
ring, and (found only by this phase's own isolation spot-check) giving the
hybrid-vs-non-hybrid signup-day draw its own dedicated per-ring `Random` too
— `randint`'s rejection sampling consumes a variable number of words
depending on the range argument, so two branches with different bounds are
not isolated merely by drawing the same *number* of `randint` calls.

- [x] **manual** — spot-check: two runs differing only in
      `p_ring_instrument_funded` produce byte-identical `fam00` membership,
      first account id, and total transaction count (verified interactively,
      corrected here from a "scripted" label the row never earned — the
      row's own text already said this is not a permanent test, since it
      requires running the generator twice under different configs, which no
      fixture in `tests/` ran at the time this row was written. Tasks 3-4
      later added exactly this kind of two-config comparison as ad hoc
      verification in their own reports, still not as a `tests/` fixture)
- [x] **scripted** — the weight-gate test refuses `B_equal`,
      `C_separation_proportional` (newly refused this run), and
      `E_drop_temporal`, and confirms `A_baseline` and `D_drop_flagged` both
      remain feasible and tie *(test 19)*
- [x] **manual** — `weight_search_protocol.md` re-run end to end: `A_baseline`
      won outright on the first pass (threshold 0.18, validation expected
      loss 4,000.00); `D_drop_flagged` ties it exactly but is a no-op against
      the current weights, so the fold-back rule (§5 rule 4) was not invoked
- [x] **scripted** — `experiments/weight_policy.json` carries the current
      config fingerprint, and the pipeline's copy into `out/` matches it --
      caught by config-fingerprint agreement at `Artifacts` load time
      (`test_api.py` test 01/02) and the live-recomputing regression tests
      (test 19, test 20), not by test 18 (see the Phase 11 row above for why)
- [x] **scripted** — the binary/three-way collapse at `t_lo = t_hi` reproduces
      the current frozen expected loss (4,000.00 at threshold 0.18) exactly
      *(test 20)*
- [x] **manual** — `abstention_protocol.md` re-run end to end: the free
      search selects the degenerate band `t_lo=0.18, t_hi=0.18` (identical to
      the binary policy), held-out expected loss 74,595.13 against the
      binary policy's 74,595.13 -- a 0% change, not a reduction, because the
      two policies are bit-for-bit identical on every held-out row
- [x] **manual** — `implementation_plan.md` "Phase 10-12" reports the
      account-age-confound target honestly: `transaction_level` no longer
      reaches held-out F1 1.0000 (now 0.5833, below even `shared_device_only`
      at 0.6957), and the shipped `ring_score` (0.7778) still beats it
      outright -- the direction held, the margin and the ranking among
      baselines both moved
- [x] **manual** — `riskmesh/api/payloads.py`'s per-signal bug-attribution
      note fixed: each zero-weighted signal maps to the RISK item that
      actually zeroed it (`ip_sharing` -> RISK-001, `instrument_sharing` ->
      RISK-004, `merchant_concentration` -> RISK-002) instead of a single
      hardcoded `"RISK-001"` string; `tests/test_api.py` test 07 checks the
      per-signal mapping, not just that a note is present
- [x] **manual** — every document quoting a weight-search or abstention
      number, a "minority" fraction that is actually >= 0.5, a stale
      "seven signals" count, or the weight-search winner's name, re-checked
      against the fresh `out/` and corrected

## Tasks 1-7 — benchmark rebuild, re-freeze, and a fifth test suite

Tasks 1-7 (a separate plan, `integrity-and-scope-closure`) raised the
population, added four ring types and three hard-negative cluster types on
top of Phase 12's benchmark, made the four frozen-policy stages regenerable
from a single `riskmesh/freeze.py` entry point, re-ran all four protocols
against the rebuilt benchmark, and added the Tier 2/3 baseline rows, a real
threshold sweep, and bootstrap confidence intervals. Current config
fingerprint **`fdf4fc217347d36b`**. This section rows every check those tasks
added across all five suites; the ring/cluster-injector rows (01b, 03b-03e,
06b) are listed under Phases 2-3 above since that is where they logically
belong, not repeated here.

### `tests/test_riskmesh.py` — rows 19-27 (current benchmark)

- [x] **scripted** — the weight-gate test refuses `B_equal` and
      `C_separation_proportional`, and confirms `A_baseline`,
      `D_drop_flagged` and `E_drop_temporal` all remain feasible and tie
      *(test 19 — same check as Phase 11/12's row, re-verified against the
      current fingerprint; `E_drop_temporal` moved from "refused" in Phase 12
      to "feasible and tying" here because Task 6's re-freeze folded its
      winning vector into `A_baseline` itself)*
- [x] **scripted** — `abstention.three_way_stats(t_lo=t_hi=0.18)` reproduces
      the frozen binary expected loss **107,168.10** exactly at this fixed
      regression-anchor threshold — independent of whatever band
      `abstention_policy.json` currently freezes (0.10/0.20, non-degenerate;
      see the "Decision policy" figures in README) *(test 20; this anchor has
      moved five times across Tasks 3-4 as the population and weight vector
      changed — see the test's own docstring change-history comment)*
- [x] **scripted** — the ablation table's `full` row reproduces
      `eval_report.json` exactly (F1 0.7500 @ threshold 0.22) *(test 21)*
- [x] **scripted** — the six ablation groups partition all 8 signals with no
      overlap and no gap; the predicted `ip` no-op (already zero-weighted, so
      removing it changes nothing) holds exactly *(test 22)*
- [x] **scripted** — all five value-swept PRD baselines (`random`,
      `shared_device_only`, `shared_ip_only`, `transaction_level`,
      `ring_score`) are present and each is read from its own frozen cutoff
      exactly once; `_freeze_cutoff` refuses a view containing test rows
      *(test 23, renamed from a 5-row exact-list check to a prefix check once
      the table grew to 7 rows in Task 7)*
- [x] **scripted** — the baseline table reports the shipped scorer
      (`ring_score`) at its own frozen threshold (0.22, F1 0.7500), not
      re-swept independently of `out/threshold.json` *(test 24, unchanged by
      Task 7)*
- [x] **scripted** — the baseline table carries all seven rows (five swept +
      `xgboost_scorer` + `gnn_scorer`); `xgboost_scorer` is `feasible: false`
      with `held_out: null` and a status naming both the refusal and that no
      held-out read was taken; `gnn_scorer`'s `held_out` matches
      `graphsage_policy.json`'s frozen record exactly, and its
      `tier1_reference` matches `weight_policy.json`'s own `held_out`
      (threshold 0.10, F1 0.5432, expected loss 92,263.55) — **and,
      adversarially, that `tier1_reference["f1"] != ring_score["held_out"]
      ["f1"]`**, so a future edit cannot silently reintroduce the
      mixed-operating-point pairing a coordinator review caught in Task 7
      *(test 25, new)*
- [x] **scripted** — the threshold sweep has 101 rows (0.00-1.00 step 0.01),
      computed on validation only, every row carries all six PRD-named
      columns (precision, recall, FP count/rate, FN count/rate, review
      count/rate, expected loss) plus `threshold`/`selected`, exactly one row
      is `selected: true` and its threshold equals `out/threshold.json`'s;
      the pre-existing 4-row ladder (`flag_nothing`/`flag_everything`/
      `binary`/`three_way`) is unchanged *(test 26, new)*
- [x] **scripted** — `bootstrap_ci.json` is byte-identical across two runs at
      the same seed (5,000 resamples); carries exactly the four PRD metric
      keys (precision, recall, F1, FPR); each interval brackets its point
      estimate and has nonzero width at n=112 test components; reported as
      measured rather than tightened for appearance (F1 CI [0.5946, 0.8750],
      width 0.2804) *(test 27, new)*
- [x] **scripted** — `test_18_reproducible_outputs`'s hardcoded file list
      grew from 11 to 12 entries with `bootstrap_ci.json` added *(existing
      test, extended in Task 7; the two ML frozen records,
      `xgboost_policy.json`/`graphsage_policy.json`, are not in this list —
      they are copied byte-for-byte from `experiments/` by `__main__.py`
      rather than regenerated by the plain-pipeline fixture this test uses,
      so their reproducibility is covered instead by `test_freeze.py` and by
      Task 1's report's own diff verification)*

### `tests/test_api.py` — 10 checks (was 9)

- [x] **scripted** — artifacts load and all **10** fingerprinted files (up
      from 9; Task 2 added `xgboost_policy.json`/`graphsage_policy.json`,
      Task 7 added `bootstrap_ci.json`) agree on `config_fingerprint`
      *(test 01, message now derived from `len(_FINGERPRINTED)` instead of a
      hardcoded number)*
- [x] **scripted** — mixed-vintage artifacts raise `ArtifactsNotFrozen`, not
      a warning *(test 02, unchanged)*
- [x] **scripted** — the contribution sum reproduces the frozen score exactly
      for all 336 components (drift <= 1.11e-16) *(test 03, unchanged)*
- [x] **scripted** — `bands.action_for` agrees with
      `abstention.three_way_stats` on every test component (allow 54, review
      32, escalate 26) *(test 04, unchanged)*
- [x] **scripted** — the peer-selection rule is stable over 50 shuffles for
      every flagged component *(test 05, unchanged)*
- [x] **scripted** — `/metrics`, `/threshold-analysis`, `/benchmark` all
      carry the frozen headline figures (three-way 75,529.35 vs binary
      92,263.55; F1 0.75; escalated false positives; weight candidates
      refused) *(test 06, unchanged)*
- [x] **scripted** — `/evidence` for the top-ranked test component keeps the
      zero-weighted signals (`ip_sharing`, `instrument_sharing`,
      `merchant_concentration`) with their own RISK-001/RISK-004/RISK-002
      notes attached per-signal, not one hardcoded note *(test 07, unchanged
      since Phase 12)*
- [x] **scripted** — the audit log round-trips, skips a torn line, filters by
      component, and refuses an unknown action *(test 08, unchanged)*
- [x] **scripted** — `/rings` ranks by score descending; the action filter
      returns the right escalate/review counts *(test 09, unchanged)*
- [x] **scripted** — `benchmark()`/`threshold-analysis()` serve the seven-row
      baseline table (Tier 2 refused, Tier 3 present), the 101-row threshold
      sweep with all six columns, and `bootstrap_ci` verbatim (not
      recomputed) *(test 10, new, Task 7)*

### `tests/test_ml.py` — 4 checks (XGBoost, Tier 2), unaffected by Tasks 3-7 in mechanism, re-verified against the current benchmark

- [x] **scripted** — the difficulty gate refuses `X4_unregularised`
      (`PanelGateFailure` on the current benchmark — see README's Tier 2
      writeup for why the refusal mechanism flipped from "degenerate
      constant predictor" to "over-separation" between the old and new
      benchmark sizes; the gate still fires, by a different route) *(test 01)*
- [x] **scripted** — `select_xgboost_model` refuses a design view containing
      a test row (`DesignSplitViolation`, Task 2) *(test 02)*
- [x] **scripted** — `evaluate_frozen_ml_policy` raises `MLPolicyNotFrozen`
      before the freeze file exists *(test 03)*
- [x] **scripted** — determinism: refitting each of the 4 candidates twice
      gives bit-identical validation predictions on the installed xgboost
      version *(test 04)*

### `tests/test_gnn.py` — 4 checks (GraphSAGE, Tier 3)

- [x] **scripted** — `gated_expected_loss()` refuses a hand-built,
      deliberately over-separated candidate set (`DifficultyGateFailure`),
      checked against a synthetic 40-candidate design rather than against
      whichever real `G*` candidate happens to over-separate this run's
      population — Task 4 found the original version of this check (which
      asserted `G3_unregularised` specifically gets refused) broke once the
      larger population meant no real GraphSAGE candidate over-separated any
      more, and rewrote it as this property test so it no longer depends on
      one hyperparameter configuration's luck against one run's data.
      `G3_unregularised` is still run and reported informationally
      (`feasible (pbmn 1.0 -- does not over-separate at this population)` on
      the current benchmark) but nothing is asserted on its outcome *(test 01,
      rewritten by Task 4; see its report for the full before/after)*
- [x] **scripted** — `select_gnn_model` refuses a design view containing a
      test row *(test 02)*
- [x] **scripted** — `evaluate_frozen_gnn_policy` raises `GNNPolicyNotFrozen`
      before the freeze file exists *(test 03)*
- [x] **scripted** — determinism: refitting each of the 3 candidates twice
      gives bit-identical validation predictions on the installed torch
      version (CPU, `torch.manual_seed` + `use_deterministic_algorithms`)
      *(test 04)*

### `tests/test_freeze.py` — 1 check (new suite, Task 1)

- [x] **scripted** — `freeze_weights()`, run against a scratch path (never
      the real `experiments/weight_policy.json`), reproduces the
      **committed** record's `winner` and `sensitivity.distinct_winners`
      exactly — the check that proves `riskmesh/freeze.py` (which wires up
      the existing `select_*`/`freeze_*` functions rather than reimplementing
      selection logic) actually regenerates what is on disk, for the
      `weights` stage. Scoped to `weights` only, so it never imports
      `riskmesh.ml`/`riskmesh.gnn` and holds Tier 0's zero-dependency
      guarantee (Global Constraint G7) even though `riskmesh/freeze.py`
      itself also drives the xgboost/graphsage stages *(test 01)*

### Suite counts, current

```
python tests/test_riskmesh.py   -> 33/33
python tests/test_api.py        -> 10/10
python tests/test_ml.py         ->  4/4
python tests/test_gnn.py        ->  4/4
python tests/test_freeze.py     ->  1/1
```

`test_freeze.py` is a **fifth** suite, added whole by Task 1. README.md's
"Run it" section, which used to list only the first four `tests/test_*.py`
commands, now lists all five.
