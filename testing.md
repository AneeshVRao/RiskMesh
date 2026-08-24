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
