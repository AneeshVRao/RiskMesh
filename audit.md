# Audit — Phase 9 (Tier 0 complete) · 2026-08-25

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
18/18; pyright reports 0 errors across the package.

Final numbers: 5644 transactions, 806 accounts, 100 candidate components
(402 singletons dropped), largest component 1.1% of accounts, all 20 NAT IPs
capped. Splits 38/31/31 components, 8 positive each. Non-triviality verdict
PASS on all five checks. Held-out at the frozen threshold 0.27: precision 0.533,
recall 1.000, F1 0.696, FPR 0.304, ring recovery 8/8.

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
