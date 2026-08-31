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

- [x] **scripted** — transaction count is 5000 ±10%
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
- [x] **scripted** — every family cluster shares ≥1 attribute type with at least
      one ring pattern *(test 6, hard negatives are hard)*

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
      *(test 19; FLAG-level — currently flags `merchant_concentration`,
      tracked as RISK-002)*

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
- [x] **manual** — `implementation_plan.md` "Phase 10-11" reports the
      account-age-confound target honestly: `transaction_level` no longer
      reaches held-out F1 1.0000 (now 0.7143), and the shipped `ring_score`
      (0.8750) beats it outright
- [x] **manual** — every document quoting a weight-search or abstention number
      (`weight_search_protocol.md`, `abstention_protocol.md`,
      `deferred_decisions.md`, `bugs.md` RISK-004, `implementation_plan.md`,
      `README.md`) updated to the re-frozen figures

## Phase 12 — RNG-isolation fix in `_inject_rings`, second re-freeze

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

- [x] **scripted** — spot-check: two runs differing only in
      `p_ring_instrument_funded` produce byte-identical `fam00` membership,
      first account id, and total transaction count (verified interactively;
      not a permanent test, since it requires running the generator twice
      under different configs, which no fixture in `tests/` currently does)
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
