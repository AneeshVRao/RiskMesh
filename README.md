# RiskMesh

Coordinated-abuse-ring detection for the Razorpay AI Buildathon (Track 02).
Defense-only: it finds rings and hands them to an analyst. Nothing is ever
auto-blocked.

The goal is not a leaderboard number. It is a benchmark you can hand a judge
without flinching — data that is not trivially separable, labels that never
reach the detector, rings that never straddle a split, and a threshold that was
never fitted on the test set. Where the results are unflattering, they are
printed on the Benchmark tab rather than left out.

---

## Run it

```bash
# 1. the benchmark — generate, graph, score, split, evaluate
python -m riskmesh                  # writes 12 files to out/

# 2. the console
python -m uvicorn riskmesh.api.main:app --port 8000     # API
python -m http.server 8080 -d mockups                   # UI
#    then open http://127.0.0.1:8080/index.html
```

```bash
python tests/test_riskmesh.py       # 25 checks — pipeline, protocol, reproducibility
python tests/test_api.py            #  9 checks — payloads, bands, audit log
python tests/test_ml.py             #  4 checks — XGBoost gate, freeze guard, determinism
python tests/test_gnn.py            #  4 checks — GraphSAGE gate, freeze guard, determinism
```

The pipeline and its tests need **CPython 3.10+ and nothing else** — no numpy,
no pandas, no networkx. `requirements.txt` carries `fastapi` and `uvicorn`, and
those two are needed *only* by `riskmesh/api/routes.py` and `main.py`. That is
what makes "reproducible from a clean environment" true rather than aspirational.

---

## What it does

A ring is not a transaction. It is a set of accounts wired together by shared
infrastructure — one device, one card, one burst of activity at one merchant.
RiskMesh builds a heterogeneous graph over accounts, devices, IPs, instruments
and merchants, takes connected components as candidates, and scores each
component on eight signals.

The hard part is not finding shared infrastructure. It is **not flagging the
family**. A household shares a device *and* a home IP *and* often a card — the
same structure a ring shares. The whole benchmark exists to keep that
distinction honest.

Four screens, all reading the same frozen artifacts:

| Screen | What it answers |
|---|---|
| **Control Center** | What needs attention now, and what the policy costs |
| **Investigator** | Why this component scored what it scored |
| **Threshold & Cost** | Why this operating point and not a different one |
| **Benchmark** | Should you believe any of the above |

---

## Read this before the numbers

Three findings that a demo could hide and this one does not.

**1. The graph score now beats the strongest non-graph rule — this took three
phases to get right, and the fix is narrower than it sounds.** The original
build found a transaction-level baseline — "every transaction from an account
under 30 days old" — separating the held-out split perfectly (F1 1.0000)
where the ring scorer reached 0.8000, because every ring account was uniformly
young. Phase 10 added a second ring mechanism (a majority of rings, tuned to
70%, funded through a shared instrument pool, drawing signup age from a much
wider range) specifically to break that confound; Phase 11 re-ran the weight
search and abstention protocols against the settled result; Phase 12 then
found and fixed an RNG-isolation bug in that same mechanism
(`riskmesh/generate.py`) and re-ran both protocols again. On the current
benchmark, `transaction_level` reaches held-out F1 **0.5833** and the shipped
`ring_score` reaches **0.7778** — the graph wins the comparison this build was
built to win, by a wider margin than Phase 10/11 reported. It is not a clean
sweep: `shared_device_only` (0.6957) still trails the graph score, but this
run it also beats `transaction_level` (0.5833) — a naive per-transaction rule
is no longer even the strongest non-graph baseline. See
`implementation_plan.md` "Phase 10-12" for the full table and the
account-age-cut sensitivity that confirms the mechanism.

**2. No structural or behavioural group is shown to cost held-out F1 when
removed, this run.** Leave-one-group-out, re-run on the current benchmark:
removing `ip` and `instrument` cost nothing (unchanged F1), and removing
`device`, `temporal`, or `behavioral_refund` all *improve* held-out F1 (to
0.8750, 0.8421, and 0.8750 respectively) — a different, and notably weaker,
result than the original run's `instrument` finding or Phase 10/11's
`behavioral_refund` finding, both of which showed a group costing F1 when
removed. No weight was changed on the strength of this — re-weighting on a
held-out read is exactly the selection this benchmark is built to rule out,
and a table where every row ties or improves is itself a finding to report
rather than to quietly stop mentioning.

**3. The weight search confirmed the hand-set incumbent outright, in one pass,
this time.** The Phase 12 re-run of `weight_search_protocol.md` did not need
to fold anything back: `D_drop_flagged` — which zeros `instrument_sharing` and
`merchant_concentration`, the two signals RISK-004 and RISK-002 had flagged —
still ties `A_baseline` exactly on validation expected loss, but it is a
no-op this time (those two signals are *already* zero in the current
`A_baseline`, folded in during Phase 11), so with no sharper difficulty
margin to win the tie-break on, the tie resolves to the incumbent and the
search converges on the first pass. `temporal_burst` (0.309,
`deferred_decisions.md` D1, still open) remains the largest weight and still
has not been shown to separate rings from families rather than from
background.

The honest claim this build supports: **the three-way abstention policy, the
cost model, and — as of Phase 12 — the graph score's win over the strongest
non-graph baseline all earn their keep on this benchmark.** Anything stronger
about a general graph-vs-transaction claim still needs more ring types.

---

## What it writes to `out/`

| File | Contents |
|---|---|
| `transactions.csv` | The transaction stream. **No label columns** — the detector's only input. |
| `labels.csv` | Ground truth, kept separate on purpose. |
| `components.csv` | Every candidate: split, score, and each signal's raw / normalised / detail. |
| `graph_edges.json` | Typed nodes, degrees and edges per component — what the UI draws. |
| `integrity_report.json` | Cardinalities, reuse histograms, class balance, non-triviality panel. |
| `threshold.json` | The binary threshold, selected on validation, frozen before test is read. |
| `weight_policy.json` | The weight search: five candidates, three gate refusals. |
| `abstention_policy.json` | The Allow / Review / Escalate band. |
| `eval_report.json` | Held-out metrics at the frozen threshold. |
| `baselines.json` | The five PRD baselines, each with its own frozen cutoff. |
| `ablations.json` | Full model vs. each signal group removed. |

Every file carries the seed, the config fingerprint and the Python version.
`tests/test_riskmesh.py` check 18 regenerates all eleven and compares byte for
byte.

---

## How the data is built

**Normal behaviour is correlated, not random rows.** Each account has a sticky
merchant set on a popularity power law, its own device and home IP, a personal
amount multiplier, lognormal activity, diurnal timestamps, and a contiguous
activity spell. Around 20 carrier-NAT IPs are each shared by 55–89 unrelated
accounts — the common infrastructure the graph has to survive.

**Rings (24) share a device.** Freshly-registered thin-history accounts routing
~68% of traffic through one device, with partial card overlap, elevated refunds,
and *usually* a coordinated burst. Usually is the point: 30% of rings never
burst, refund rates vary per ring, and members keep their own traffic. A ring
that always does everything is separable by one rule.

**A majority of rings (70%, Phase 10) are additionally pool-funded.** Instead
of the flat partial-instrument overlap above, a hybrid ring funds every member
through a small shared pool of instruments, and draws signup age from a much
wider range (5-400 days) rather than uniformly young. This exists specifically
to break the account-age confound recorded below in "Read this before the
numbers" — a hybrid ring's members are a mix of fresh mules and older
compromised/synthetic accounts. The remaining 30% of rings are untouched, so
the benchmark still contains the original mechanism alongside the new one.

**Families (24) are the hard negative.** A household shares a device *and* a
home IP *and* often a card. What differs is behaviour: real tenure, activity
spread across its period, diverse merchants. Households run up to 8 accounts, as
wide as a ring, which is what keeps the device-only baseline honest.

**Unlabelled noise matters too.** 70 background account pairs share a device with
no label at all. Without it, "two accounts share a device" separates the classes
perfectly and the benchmark measures nothing.

### Graph hygiene

1. **Merchants never link.** Everyone touches the popular merchants; merchant
   edges would merge the whole population. They stay as evidence only.
2. **Degree cap.** An attribute used by more than `max_ip_degree` (8),
   `max_device_degree` (12) or `max_instrument_degree` (9) distinct accounts is
   common infrastructure and stops linking. Caps sit above the largest legitimate
   ring or household, so nothing real is capped away.
3. **Minimum edge weight.** An account must use an attribute ≥ 2 times to link
   through it. One incidental touch should not weld two populations together.

Union-find over what survives; components with ≥ 2 accounts become candidates.

---

## The scorer

Weighted sum of eight signals, each with a raw value, a normalised [0,1] value
and a human-readable detail string. Weights sum to exactly 1.00.

| Signal | Weight | Measures |
|---|---|---|
| `temporal_burst` | 0.309 | Most distinct accounts converging on one merchant in 30 min |
| `device_sharing` | 0.272 | Most accounts on one device |
| `instrument_pool_concentration` | 0.148 | Accounts funded through one small shared instrument pool (Phase 10) |
| `failure_refund_rate` | 0.148 | Refund + failure rate vs the population baseline |
| `account_newness` | 0.123 | Inverted median account age |
| `instrument_sharing` | **0.00** | Most accounts on one payment instrument — see below |
| `merchant_concentration` | **0.00** | Share of traffic at one merchant — see below |
| `ip_sharing` | **0.00** | Most accounts on one non-common IP — see below |

**Three signals carry zero weight, each deliberately, each documented as a
finding rather than an oversight.** `ip_sharing` was mis-signed from the start
(RISK-001): families ran 0.701 against rings' 0.162, pushing legitimate
clusters up and rings down — the ring injector places no shared IP at all, and
the original definition counted transactions rather than accounts, making it a
back-door detector keyed on the *absence* of a household. `instrument_sharing`
and `merchant_concentration` were zeroed by Phase 11's re-run weight search
(`weight_search_protocol.md` §8), which picked the policy that zeros exactly
RISK-004's and RISK-002's flagged signals over the hand-set incumbent, on cost
grounds, not by hand. All three stay computed as evidence.

**Every currently-weighted signal now separates rings from families in the
correct direction** — a change from the original Tier 0 run, where the
highest-weighted signal (`temporal_burst`) separated rings from background
only, and `instrument_sharing` actively favoured families. Ring-minus-family
deltas on train+validation: `account_newness` +0.4085, `temporal_burst`
+0.2812, `device_sharing` +0.1534, `failure_refund_rate` +0.1260,
`instrument_pool_concentration` +0.0755. The only mis-signed signal is
`ip_sharing` (**-0.5357**), which is exactly why it stays at weight 0.00
(RISK-001) rather than evidence the fix is incomplete. `instrument_sharing`,
also zero-weighted, is now barely mis-signed either way (+0.0078, up from the
original run's -0.0938 — see `bugs.md` RISK-004's forward note) as a side
effect of the same generator change, not because anyone fixed it directly.

---

## Evaluation protocol

**Ground-truth rule:** a component is positive iff ≥ 50% of its accounts belong
to a single injected ring. This is a labelling convention *for this benchmark*,
not a definition of a risk ring — a chain of pairwise-shared attributes can
spread one ring across a component where no single ring holds a majority, and
this rule scores that negative. A known scope limit, not a bug.

**The split is chronological and ring-level:** train days 0–17, validation 18–23,
test 24–29. Labelled components take their split from the generator's explicit
`active_period` — the split is a property of how a cluster was *built*, not of
the data it happened to emit. Each one's median-timestamp period is computed
independently and asserted equal; a mismatch fails the run rather than producing
a chronology that is fiction.

**The freeze is load-bearing, not decorative.** `select_threshold()` receives
validation candidates only — its signature makes passing test data impossible —
and the choice is written to `threshold.json` before any test data is read. The
runner then reads that file back. Same discipline for the weight policy, the
abstention band, and every row of the baseline and ablation tables: each frozen
cutoff is selected on validation and the held-out split is read once.

### The non-triviality panel

Computed on **train + validation only**, because those are the numbers you would
tune the generator against. Six checks, each printed next to its bound:

| Check | Bound |
|---|---|
| score distributions overlap | must overlap |
| positives below top negative | ≥ 20% |
| hard negative inside positive range | ≥ 1 |
| no single signal separates perfectly | F1 < 1.0 — **fails the run** |
| shared-device-only baseline | F1 < 0.85 |
| no weighted signal mis-signed | flag, not fail |

Max-F1 is swept in **both** threshold directions (`>= t` and `<= t`). Three
signals here separate in the inverted direction, and a one-directional sweep
would understate them badly — it would also miss a signal separating *perfectly*
while inverted, which is exactly what the hard-failure guard exists to catch.

---

## Current figures

After `rm -rf out && python -m riskmesh`. Fingerprint `c3ee14627c2c2ce2`,
seed 20260824, Python 3.12.10. Re-frozen in Phase 12 after fixing a real
RNG-isolation bug in `_inject_rings` (`riskmesh/generate.py`'s module
comment) that Phase 10 introduced — the fingerprint is unchanged (it hashes
config fields, not generator code) but every figure below moved anyway,
because the fix changes actual generator output.

**Dataset** — 6,052 transactions, 799 accounts, 996 devices, 916 IPs, 739
instruments, 40 merchants. 24 rings (70% hybrid pool-funded — a majority, not
a minority), 24 families. 100 candidate components (402 singletons dropped),
largest 9 accounts (1.1%), 20 NAT IPs capped. Non-triviality verdict **PASS**;
shared-device baseline F1 0.7442.

**Operating point.** Weight policy re-run (`weight_search_protocol.md`,
Phase 12) against five pre-declared candidates behind three hard feasibility
gates: `A_baseline` won outright in a single pass this time — `D_drop_flagged`
still ties it exactly (it is a no-op: the current `A_baseline` already
carries `instrument_sharing`/`merchant_concentration` at weight 0.00 from
Phase 11's fold-back), but with no sharper `positives_below_max_negative` to
win the tie-break on, the tie resolves to the incumbent and the fold-back
rule never triggers. Three of five candidates are now refused by the
difficulty gate (`B_equal`, `C_separation_proportional`, `E_drop_temporal`),
against two in Phase 10/11. Held out at threshold 0.18, one read: precision
0.7000, recall 0.8750, F1 0.7778, FPR 0.1304, ring recovery 7/8, expected loss
**74,595.13**.

> How to describe this: we established an explicit cost model and selected
> among integrity-valid policies under it. Not "optimized to minimize the cost
> of missed fraud" — the winner's *validation* operating point has fn = 0, so
> `C_fn` never enters the validation total. Held-out is a different story this
> run: one missed ring alone (`C_fn` 68,399.84) accounts for most of the
> 74,595.13 figure above, which is why a single point estimate at this cost
> ratio should always be read next to the sensitivity table, not instead of it.

**Decision policy.** A three-way band layered on the frozen scorer, which is
unchanged and not reopened:

```
score < 0.18   -> Allow
score >= 0.18  -> Escalate      (Review is empty: t_lo == t_hi == 0.18)
```

Both boundaries were freely searched behind a pre-declared 25% review-coverage
gate, minimised on validation, frozen to disk before test was read. This run
the search lands on a **degenerate band** — `t_lo = t_hi = 0.18` — because
`A_baseline` reaches a perfect validation confusion matrix (fn = 0 *and*
fp = 0) at that threshold, leaving Review nothing to rescue or waive on
either side. Held out, one read: expected loss **74,595.13**, bit-for-bit
identical to the binary policy on the same rows — a **0%** change, not a
reduction. Every held-out error (3 family false positives, 1 missed ring)
sits either well inside Escalate or before Allow's boundary; none of them are
the near-miss case a review band exists to catch on this particular draw.

`deferred_decisions.md` D3 (the review-cost double-charge) is **resolved**, not
a caveat, as of Phase 10 — there is one cost model to report, which this run's
finding (three-way == binary exactly) demonstrates rather than complicates.
The review tier still assumes an analyst resolves a deferred case correctly —
a stated assumption, not a measurement.

**Baselines** (each at its own frozen cutoff, held-out F1):

| Baseline | Sees graph | F1 | FPR |
|---|---|---|---|
| `ring_score` | fully | **0.7778** | 0.1304 |
| `transaction_level` | none | 0.5833 | 0.3913 |
| `shared_device_only` | one rule | 0.6957 | 0.3043 |
| `shared_ip_only` | one rule | 0.5161 | 0.6522 |
| `random` | none | 0.0000 | 0.0000 |

The shipped scorer still beats every other baseline outright, but
`transaction_level` has fallen behind `shared_device_only` too this run — it
is no longer even the strongest non-graph baseline, a further move in the
same direction as the pre-Phase-10 reversal. See "Read this before the
numbers" above and `implementation_plan.md` "Phase 10-12" for the full story.

**Ablations** (leave-one-group-out, each with its own frozen threshold):

| Removed | F1 | Δ | Rings found |
|---|---|---|---|
| — full model | 0.7778 | — | 7/8 |
| `behavioral_refund` | 0.8750 | **+0.0972** | 7/8 |
| `device` | 0.8750 | **+0.0972** | 7/8 |
| `ip` | 0.7778 | 0.0000 | 7/8 |
| `temporal` | 0.8421 | **+0.0643** | 8/8 |
| `instrument` | 0.7778 | 0.0000 | 7/8 |

**No group's removal costs held-out F1 this run** — every row ties or
improves on the full model. This is a different result from Phase 10/11,
where `behavioral_refund` and `instrument` both cost F1 when removed; no
weight was changed on the strength of either reading, per the same rule.

**Tier 2 — XGBoost scorer.** `xgboost_protocol.md`, frozen before any
candidate was scored: four pre-declared `XGBClassifier` configurations over
the linear scorer's own 8 signals, gated by the identical three feasibility
gates above, unchanged. **All four were refused** — three (`X1`–`X3`)
degenerate to a constant prediction on this benchmark's ~30-row training
split (their `min_child_weight` never clears on a component this small), and
the deliberately-overfit `X4` genuinely over-separates, exactly as it was
included to demonstrate. **No candidate reached a held-out read, so XGBoost
does not beat Tier 1 (F1 0.7778 / expected loss 74,595.13) — there is no
XGBoost number to compare, not an unfavourable one.** Full mechanism writeup
in `xgboost_protocol.md` §8; frozen record in `experiments/xgboost_policy.json`.

**Tier 3 (stretch) — GraphSAGE scorer.** `graphsage_protocol.md`, frozen
before any candidate was scored: three pre-declared hand-rolled GraphSAGE
architectures (plain `torch` tensor ops, no `torch_geometric`/`dgl`) over a
per-component graph built from `riskmesh.graph.Component` — structural node
features only (one-hot type + degree), deliberately not the linear scorer's
8 signals, gated by the identical three feasibility gates above, unchanged.
**One candidate, `G1_single_layer` (the smallest architecture), cleared all
three gates** — a different outcome from Tier 2's XGBoost attempt, where none
did. The two larger, 2-layer candidates both failed via genuine
over-separation. Refit on train+validation and read once: F1 **0.5000**,
expected loss **83,579.43** — **GraphSAGE does not beat Tier 1** (F1 0.7778 /
expected loss 74,595.13): it clears the validation gate with margin but
generalises substantially worse to the held-out test split, the same shape
of validation-to-test gap the weight search's own `weight_search_protocol.md`
§8 already reported once. Full mechanism writeup in `graphsage_protocol.md`
§8; frozen record in `experiments/graphsage_policy.json`.

---

## The console

FastAPI over the frozen artifacts. Six of the eight endpoints are pure file
reads; the API computes almost nothing, so the screen cannot disagree with the
benchmark.

```
GET  /rings                    ranked queue, filterable by action
GET  /rings/{id}               one component
GET  /rings/{id}/evidence      signals, decomposition, graph, comparison, audit
POST /rings/{id}/review        the one write path -> out/audit_log.jsonl
GET  /metrics                  held-out metrics + triage counts
GET  /threshold-analysis       cost derivation and the expected-loss ladder
GET  /benchmark                integrity panel, baselines, ablations
POST /explain                  grounded narration for one component
```

**Writes are not optimistic.** A click posts, and the audit trail is then
*re-read from the server* rather than patched locally, so a failed write cannot
render as a good one. The log is append-only JSONL; each record embeds the full
evidence snapshot plus its sha256, rather than referencing `components.csv`,
so the record still means something after a regeneration changes the file.

**`/explain` is the deterministic fallback only — no model is wired.** The
request carries a component id and nothing else; the server reads the frozen
evidence itself, so a caller cannot induce a narration the detector never
supported. Every clause in the sentence is a `detail` string produced by
`score_component()`, and the console prints which signals it was grounded in
directly under it. The panel loads after the deterministic evidence and never
gates it: kill the endpoint and the ledger, graph and decomposition still render.

---

## Not built, and why

| | |
|---|---|
| **Four other ring types, three other hard negatives** | The PRD's Initial Development Slice starts with one of each; widening it re-fingerprints every frozen number in the build. This is the change that would fix finding #1 above. |
| **A shipped GraphSAGE scorer** | Attempted as Tier 3 stretch work (`graphsage_protocol.md`); one candidate cleared the feasibility gate but its held-out F1 (0.5000) and expected loss (83,579.43) both trail Tier 1's, so nothing from this phase replaces the frozen linear scorer. |
| **Bootstrap confidence intervals** | The PRD calls these optional polish that must never delay Tier 1. |
| **A real LLM behind `/explain`** | The grounding contract and fallback are built and demonstrated; the model is the first thing the PRD says to cut. |
| **Auth, a database, deployment** | Explicitly out of scope for the buildathon. |

---

## Project files

```
riskmesh/config.py       every knob + the config fingerprint
riskmesh/generate.py     entities, correlated traffic, both injectors
riskmesh/graph.py        typed edges, hygiene caps, union-find components
riskmesh/score.py        eight signals, raw + normalised + detail
riskmesh/split.py        chronological ring-level split
riskmesh/integrity.py    integrity report + non-triviality panel
riskmesh/costmodel.py    cost derivation, weight search, feasibility gates
riskmesh/abstention.py   the three-way band search
riskmesh/comparisons.py  the five baselines and the ablation table
riskmesh/evaluate.py     ground-truth rule, threshold freeze, metrics
riskmesh/experiment.py   the recorded signal experiments (E1-E6)
riskmesh/ml.py           XGBoost candidates, the same gates reused unchanged
riskmesh/gnn.py          hand-rolled GraphSAGE candidates, the same gates reused unchanged
riskmesh/__main__.py     the one command
riskmesh/api/            FastAPI: artifacts, bands, payloads, audit, routes
mockups/                 the four screens + api.js, the live client
tests/                   25 pipeline checks + 9 API checks + 4 XGBoost checks + 4 GraphSAGE checks
```

**Where the reasoning lives.** `implementation_plan.md` is the build log, phase
by phase. `bugs.md` carries every RISK entry with its measurements.
`deferred_decisions.md` lists what was knowingly left, with the cost.
`weight_search_protocol.md`, `abstention_protocol.md` and
`xgboost_protocol.md` are the three protocols that were frozen to git *before*
their runs — read the predictions, then the results.
