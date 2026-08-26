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
