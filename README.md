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
python -m riskmesh                  # writes 11 files to out/

# 2. the console
python -m uvicorn riskmesh.api.main:app --port 8000     # API
python -m http.server 8080 -d mockups                   # UI
#    then open http://127.0.0.1:8080/index.html
```

```bash
python tests/test_riskmesh.py       # 25 checks — pipeline, protocol, reproducibility
python tests/test_api.py            #  9 checks — payloads, bands, audit log
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
component on seven signals.

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

**1. A non-graph rule beats the graph score on this benchmark.** A
transaction-level baseline — "every transaction from an account under 30 days
old" — separates the held-out split perfectly (F1 1.0000) where the ring scorer
reaches 0.8000. The cause is the generator: every ring transaction in the test
split comes from an account ≤ 25 days old, against a negative median of 316.
Account age is doing the work the graph is credited with. Fixing it means a
second ring type whose accounts are not uniformly young, which re-fingerprints
every number in the build.

**2. The structural signals are the removable ones.** Leave-one-group-out:
removing device, IP or instrument costs **nothing**, and removing instrument
*improves* held-out F1 to 0.8889. Only the behavioural/refund group is
load-bearing (−0.1684 F1, and 2 of 8 rings lost). No weight was changed on the
strength of that — re-weighting on a held-out read is exactly the selection this
benchmark is built to rule out.

**3. About 42% of the scorer's weight is not earning it.** `temporal_burst`
(0.278) and `instrument_sharing` (0.144) both separate rings from *background*
and neither separates rings from *families*, which is the distinction that
matters. Both are deferred with measured reasons in `deferred_decisions.md`, not
quietly carried.

The honest claim this build supports is the narrow one: **the three-way
abstention policy and the cost model earn their keep; the graph score is not yet
shown to beat a simple attribute rule.** Anything stronger needs the generator
work.

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

Weighted sum of seven signals, each with a raw value, a normalised [0,1] value
and a human-readable detail string. Weights sum to exactly 1.00.

| Signal | Weight | Measures |
|---|---|---|
| `temporal_burst` | 0.278 | Most distinct accounts converging on one merchant in 30 min |
| `device_sharing` | 0.244 | Most accounts on one device |
| `instrument_sharing` | 0.144 | Most accounts on one payment instrument |
| `failure_refund_rate` | 0.133 | Refund + failure rate vs the population baseline |
| `account_newness` | 0.111 | Inverted median account age |
| `merchant_concentration` | 0.089 | Share of traffic at one merchant |
| `ip_sharing` | **0.00** | Most accounts on one non-common IP — see below |

`ip_sharing` carries **zero weight** deliberately. It was mis-signed: families
ran 0.701 against rings' 0.162, pushing legitimate clusters up and rings down.
Two causes (RISK-001, closed): the ring injector assigns no shared IP at all, so
there is no ring information in the IP dimension; and the signal counted
transactions rather than accounts, turning it into a back-door detector keyed on
the *absence* of a household. It is kept computed as evidence, ready for a
shared-IP ring type.

Only three signals separate rings from families: `account_newness` (+0.882),
`failure_refund_rate` (+0.139), `device_sharing` (+0.114). That is the honest
state of the Tier 1 baseline.

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

After `rm -rf out && python -m riskmesh`. Fingerprint `7c1e4fb2b329796c`,
seed 20260824, Python 3.12.10.

**Dataset** — 5,962 transactions, 789 accounts, 976 devices, 906 IPs, 823
instruments, 40 merchants. 24 rings, 24 families. 100 candidate components (402
singletons dropped), largest 9 accounts (1.14%), 20 NAT IPs capped. Non-triviality
verdict **PASS**; shared-device baseline F1 0.7442.

**Operating point.** Weight policy `A_baseline` retained after five pre-declared
candidates behind three hard feasibility gates — three refused, the two feasible
ones tied exactly. Held out at threshold 0.23, one read: precision 0.6667, recall
1.0000, F1 0.8000, FPR 0.1739, ring recovery 8/8, expected loss **9,392.92**.

> How to describe this: we established an explicit cost model and selected among
> integrity-valid policies under it. Not "optimized to minimize the cost of missed
> fraud" — A's loss-minimising point has fn = 0, so `C_fn` is multiplied by zero
> and never enters the total. The gate structure did real work; the false-negative
> cost it was derived from currently contributes nothing to why A won.

**Decision policy.** A three-way band layered on the frozen scorer, which is
unchanged and not reopened:

```
score < 0.23          -> Allow
0.23 <= score < 0.33  -> Review     (deferred to a human, no automatic action)
score >= 0.33         -> Escalate
```

Both boundaries were freely searched behind a pre-declared 25% review-coverage
gate, minimised on validation, frozen to disk before test was read. Held out, one
read: expected loss **6,000.00** against the binary policy's 9,392.92 on the
identical rows, at a 19.35% review rate — and **zero escalated false positives**.
All four of the binary policy's false positives are family components, and all
four land in the review band. Escalate precision 1.0000, FPR 0.0000, recall
0.7500, with the other two rings deferred rather than missed.

Two things not to over-read: the *magnitude* depends on `deferred_decisions.md`
D3 (18.8% rather than 36.1% under a corrected cost model, though the direction
and the zero-false-positive result hold either way), and the review tier assumes
an analyst resolves a deferred case correctly — a stated assumption, not a
measurement.

**Baselines** (each at its own frozen cutoff, held-out F1):

| Baseline | Sees graph | F1 | FPR |
|---|---|---|---|
| `transaction_level` | none | **1.0000** | 0.0000 |
| `ring_score` | fully | 0.8000 | 0.1739 |
| `shared_device_only` | one rule | 0.6957 | 0.3043 |
| `shared_ip_only` | one rule | 0.5161 | 0.6522 |
| `random` | none | 0.2857 | 0.6957 |

**Ablations** (leave-one-group-out, each with its own frozen threshold):

| Removed | F1 | Δ | Rings found |
|---|---|---|---|
| — full model | 0.8000 | — | 8/8 |
| `behavioral_refund` | 0.6316 | **−0.1684** | **6/8** |
| `device` | 0.8000 | 0.0000 | 8/8 |
| `ip` | 0.8000 | 0.0000 | 8/8 |
| `temporal` | 0.8000 | 0.0000 | 8/8 |
| `instrument` | 0.8889 | **+0.0889** | 8/8 |

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
| **XGBoost (Tier 2), GraphSAGE (Tier 3)** | Should-have and Could-have. The PRD's kill-switch says Tier 2 does not start until Tier 1 is stable end to end. |
| **Bootstrap confidence intervals** | The PRD calls these optional polish that must never delay Tier 1. |
| **A real LLM behind `/explain`** | The grounding contract and fallback are built and demonstrated; the model is the first thing the PRD says to cut. |
| **Auth, a database, deployment** | Explicitly out of scope for the buildathon. |

---

## Project files

```
riskmesh/config.py       every knob + the config fingerprint
riskmesh/generate.py     entities, correlated traffic, both injectors
riskmesh/graph.py        typed edges, hygiene caps, union-find components
riskmesh/score.py        seven signals, raw + normalised + detail
riskmesh/split.py        chronological ring-level split
riskmesh/integrity.py    integrity report + non-triviality panel
riskmesh/costmodel.py    cost derivation, weight search, feasibility gates
riskmesh/abstention.py   the three-way band search
riskmesh/comparisons.py  the five baselines and the ablation table
riskmesh/evaluate.py     ground-truth rule, threshold freeze, metrics
riskmesh/experiment.py   the recorded signal experiments (E1-E6)
riskmesh/__main__.py     the one command
riskmesh/api/            FastAPI: artifacts, bands, payloads, audit, routes
mockups/                 the four screens + api.js, the live client
tests/                   25 pipeline checks + 9 API checks
```

**Where the reasoning lives.** `implementation_plan.md` is the build log, phase
by phase. `bugs.md` carries every RISK entry with its measurements.
`deferred_decisions.md` lists what was knowingly left, with the cost.
`weight_search_protocol.md` and `abstention_protocol.md` are the two protocols
that were frozen to git *before* their runs — read the predictions, then the
results.
