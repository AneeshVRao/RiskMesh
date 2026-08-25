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
