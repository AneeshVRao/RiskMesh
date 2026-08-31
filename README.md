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

**1. The graph score now beats the strongest non-graph rule — this took two
phases to get right, and the fix is narrower than it sounds.** The original
build found a transaction-level baseline — "every transaction from an account
under 30 days old" — separating the held-out split perfectly (F1 1.0000)
where the ring scorer reached 0.8000, because every ring account was uniformly
young. Phase 10 added a second ring mechanism (a minority of rings funded
through a shared instrument pool, drawing signup age from a much wider range)
specifically to break that confound, and Phase 11 re-ran the weight search and
abstention protocols against the settled result. On the current benchmark,
`transaction_level` reaches held-out F1 **0.7143** and the shipped `ring_score`
reaches **0.8750** — the graph wins the comparison this build was built to
win. It is not a clean sweep: `transaction_level` still beats two of the
graph's own one-rule challengers, `shared_device_only` (0.6957) and
`shared_ip_only` (0.5000). See `implementation_plan.md` "Phase 10-11" for the
full table and the account-age-cut sensitivity that confirms the mechanism.

**2. The structural signals are still mostly the removable ones, but not the
same ones.** Leave-one-group-out, re-run on the current benchmark: removing
`ip` costs nothing (RISK-001 already zeroed it), removing `instrument` costs
−0.0972 F1, and removing `device` now *improves* held-out F1 to **0.9333** —
a different structural group than the original run's `instrument` finding.
Only the behavioural/refund group remains clearly load-bearing (−0.1691 F1,
2 of 8 rings lost). No weight was changed on the strength of this — re-weighting
on a held-out read is exactly the selection this benchmark is built to rule out.

**3. The weight search itself moved the scorer, on its own criterion, not by
hand.** The Phase 11 re-run of `weight_search_protocol.md` did not retain the
hand-set incumbent: `D_drop_flagged` — which zeros `instrument_sharing` and
`merchant_concentration`, the two signals RISK-004 and RISK-002 had flagged —
tied `A_baseline` on validation expected loss and won the tie-break on a
sharper difficulty margin. That vector was folded into `Config()`'s defaults
per the protocol's own re-freeze rule, so those two signals now carry weight
0.00 as the *shipped* default, not a rejected experiment. `temporal_burst`
(0.309, `deferred_decisions.md` D1, still open) remains the largest weight and
still has not been shown to separate rings from families rather than from
background.

The honest claim this build supports: **the three-way abstention policy, the
cost model, and — as of Phase 11 — the graph score's win over the strongest
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
| `weight_policy.json` | The weight search: five candidates, two gate refusals. |
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

**A minority of rings (70%, Phase 10) are additionally pool-funded.** Instead
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
seed 20260824, Python 3.12.10. Re-frozen in Phase 11 against the Phase 10
benchmark (hybrid pool-funded rings, the 8th signal, the D3 cost-model fix) —
every figure below moved from the pre-Phase-10 numbers.

**Dataset** — 6,059 transactions, 801 accounts, 973 devices, 910 IPs, 776
instruments, 40 merchants. 24 rings (70% hybrid pool-funded), 24 families. 105
candidate components (393 singletons dropped), largest 9 accounts (1.1%), 20
NAT IPs capped. Non-triviality verdict **PASS**; shared-device baseline F1
0.7442.

**Operating point.** Weight policy re-run (`weight_search_protocol.md`,
Phase 11) against five pre-declared candidates behind three hard feasibility
gates: `D_drop_flagged` tied the hand-set incumbent exactly and won the
tie-break on a sharper difficulty margin, so it was folded into
`Config()._default_weights()` as the new `A_baseline` and the search re-run to
a fixed point (converged in one extra iteration). Held out at threshold 0.14,
one read: precision 0.6154, recall 1.0000, F1 0.7619, FPR 0.2083, ring
recovery 8/8, expected loss **8,041.65**.

> How to describe this: we established an explicit cost model and selected
> among integrity-valid policies under it. Not "optimized to minimize the cost
> of missed fraud" — the winner's loss-minimising point has fn = 0, so `C_fn`
> is multiplied by zero and never enters the total. The gate structure did
> real work; the false-negative cost it was derived from currently
> contributes nothing to why this policy won.

**Decision policy.** A three-way band layered on the frozen scorer, which is
unchanged and not reopened:

```
score < 0.14          -> Allow
0.14 <= score < 0.23  -> Review     (deferred to a human, no automatic action)
score >= 0.23         -> Escalate
```

Both boundaries were freely searched behind a pre-declared 25% review-coverage
gate, minimised on validation, frozen to disk before test was read. Held out,
one read: expected loss **6,808.33** against the binary policy's 8,041.65 on
the identical rows, at a 15.6% review rate — a **15.3%** reduction. Unlike the
original run, this is not a clean sweep: 4 of the binary policy's 5 false
positives (all family) land in the review band, but the 5th escalates in the
three-way policy too. Escalate precision 0.8750, FPR 0.0417, recall 0.8750,
with the remaining ring deferred rather than missed.

`deferred_decisions.md` D3 (the review-cost double-charge) is **resolved**, not
a caveat, as of Phase 10 — the 15.3% figure is the only number now, not two
under separate accountings. The review tier still assumes an analyst resolves
a deferred case correctly — a stated assumption, not a measurement.

**Baselines** (each at its own frozen cutoff, held-out F1):

| Baseline | Sees graph | F1 | FPR |
|---|---|---|---|
| `ring_score` | fully | **0.8750** | 0.0417 |
| `transaction_level` | none | 0.7143 | 0.0417 |
| `shared_device_only` | one rule | 0.6957 | 0.2917 |
| `shared_ip_only` | one rule | 0.5000 | 0.6667 |
| `random` | none | 0.2000 | 0.0417 |

The shipped scorer now beats every other baseline outright, reversing the
pre-Phase-10 finding that a non-graph rule won. See "Read this before the
numbers" above and `implementation_plan.md` "Phase 10-11" for the full story.

**Ablations** (leave-one-group-out, each with its own frozen threshold):

| Removed | F1 | Δ | Rings found |
|---|---|---|---|
| — full model | 0.8750 | — | 7/8 |
| `behavioral_refund` | 0.7059 | **−0.1691** | **6/8** |
| `device` | 0.9333 | **+0.0583** | 7/8 |
| `ip` | 0.8750 | 0.0000 | 7/8 |
| `temporal` | 0.8421 | −0.0329 | 8/8 |
| `instrument` | 0.7778 | **−0.0972** | 7/8 |

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
riskmesh/score.py        eight signals, raw + normalised + detail
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
