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
python -m riskmesh                  # writes 14 files to out/

# 2. the API (either console talks to this)
python -m uvicorn riskmesh.api.main:app --port 8000

# 3a. the React console (frontend/, the PRD-named client)
cd frontend && npm install && npm run build && npm run preview
#    or `npm run dev` for a hot-reload dev server — see frontend/README.md

# 3b. or the reference client (mockups/, dependency-free fallback)
python -m http.server 8080 -d mockups
#    then open http://127.0.0.1:8080/index.html
```

```bash
python tests/test_riskmesh.py       # 33 checks — pipeline, protocol, reproducibility
python tests/test_api.py            # 10 checks — payloads, bands, audit log
python tests/test_ml.py             #  4 checks — XGBoost gate, freeze guard, determinism
python tests/test_gnn.py            #  4 checks — GraphSAGE gate, freeze guard, determinism
python tests/test_freeze.py         #  1 check  — riskmesh/freeze.py regenerates the
                                     #             committed weight-search record
                                     #             (~12 min — ten full weight searches
                                     #             over a 9-cell sensitivity grid; the
                                     #             other four suites run in seconds)
```

The pipeline and `test_riskmesh.py`/`test_freeze.py` need **CPython 3.10+ and
nothing else** — no numpy, no pandas, no networkx. `requirements.txt` carries
five pinned packages: `fastapi`/`uvicorn` for `riskmesh/api/routes.py` and
`main.py`, `numpy`/`xgboost` confined to `riskmesh/ml.py` (Tier 2), and `torch`
confined to `riskmesh/gnn.py` (Tier 3). That confinement, not the absence of
the packages, is what makes "reproducible from a clean environment" true
rather than aspirational — see each file's own dependency-decision comment.

---

## What it does

A ring is not a transaction. It is a set of accounts wired together by shared
infrastructure — one device, one card, one IP, one burst of activity at one
merchant. RiskMesh builds a heterogeneous graph over accounts, devices, IPs,
instruments and merchants, takes connected components as candidates, and
scores each component on eight signals.

The hard part is not finding shared infrastructure. It is **not flagging the
legitimate lookalike**. A household shares a device *and* a home IP *and*
often a card — the same structure a ring shares. An office shares a corporate
IP and a device pool. A hostel shares a home IP with no device overlap at all.
A retail chain's unrelated customers converge on the same merchant. The whole
benchmark exists to keep those distinctions honest.

Four screens, all reading the same frozen artifacts:

| Screen | What it answers |
|---|---|
| **Control Center** | What needs attention now, and what the policy costs |
| **Investigator** | Why this component scored what it scored |
| **Threshold & Cost** | Why this operating point and not a different one |
| **Benchmark** | Should you believe any of the above |

---

## Read this before the numbers

Three findings, reported exactly as measured, unflattering or not.

**1. The graph score finds more rings overall and dominates the case it
exists for; the strongest non-graph baseline's F1/FPR edge comes entirely
from higher precision, not higher recall.** Per-ring-type recall on the same
23 held-out positive components, `ring_score` (threshold 0.22) against
`transaction_level` (a compound rule — refund, failure, high amount, or a
thin account — at its own validation-swept cutoff):

| ring type | n | `ring_score` recall | `transaction_level` recall |
|---|---|---|---|
| device | 4 | 4/4 | 2/4 |
| hybrid | 4 | 4/4 | 4/4 |
| instrument | 7 | 5/7 | 5/7 |
| ip | 4 | **1/4** | 2/4 |
| refund | 4 | 4/4 | 4/4 |
| **total** | 23 | **18/23** | 17/23 |

`ring_score` catches more rings in total (18 vs 17) and every `device`-type
ring — the case the graph exists to catch — while a flat per-transaction
rule with no shared-attribute concept misses half of them. Read in isolation,
the bare headline numbers (`ring_score` F1 0.7500/FPR 0.0787 vs
`transaction_level`'s F1 0.7727/FPR 0.0449) would suggest the graph lost;
they do not show that the gap is precision, not recall, and would
misrepresent what the graph actually did. The graph's one real weakness is
traced, not just observed: `ip`-type rings are the graph's worst-recalled
type (1/4), because `ip_sharing` — the one signal built to detect shared-IP
convergence — carries weight 0.00, zeroed under RISK-001 in Tier 0 *before
any shared-IP ring type existed*, and none of the five pre-declared
weight-search candidates re-enables it. See `deferred_decisions.md` D5 for
the full measurement and why it is not fixed here, and "Current figures" for
the complete seven-row baseline table.

**2. The scorer's largest-weighted signal is now the one whose removal helps
held-out F1 the most; its smallest-represented group is the one whose removal
hurts it the most.** Leave-one-group-out, re-run on the current benchmark:
removing `device` (weight 0.3929, the single largest weight in the vector)
*raises* held-out F1 to 0.8696 (+0.1196) and ring recovery to 14/20. Removing
`behavioral_refund` (`failure_refund_rate` + `account_newness` +
`merchant_concentration`, combined weight 0.3929) *collapses* F1 to 0.2308
(-0.5192, only 3/20 rings). Removing `instrument`
(`instrument_sharing` + `instrument_pool_concentration`, weight 0.2143) costs
-0.0978. `ip` and `temporal` are no-ops (both already zero-weighted). No
weight was changed on the strength of this reading — re-weighting on a
held-out number is exactly the selection this benchmark exists to rule out —
but a scorer whose top weight actively costs held-out performance is a plain
finding, not a footnote. It is also now a filed, named risk: `device_sharing`
is mis-signed specifically against `family` and `office` hard negatives (both
deliberately built to converge on shared devices), masked by the panel's
pooled-all-negatives sign check the same way RISK-001 and RISK-004 were
masked before — see `bugs.md` RISK-005 and "The scorer" below.

**3. The weight search did not confirm the hand-set incumbent this pass — it
overturned it, then folded the winner back in.** Against the current
five-ring-type, four-hard-negative-type benchmark, `E_drop_temporal` (which
zeros `temporal_burst`) beat the prior incumbent outright on validation
expected loss (43,331.85 vs 57,601.30 — not a tie), because `temporal_burst`
now separates rings from each hard-negative type individually but only weakly
against all four combined — a genuine mixture effect a single weight cannot
resolve. Per the protocol's own fold-back rule, the winner became the new
incumbent; a second pass reached a fixed point in one more iteration.
**`temporal_burst` — previously the largest weight in the scorer and the
subject of `deferred_decisions.md`'s longest-open question (D1) — is now
weight 0.0000.** Four of the original eight signals now carry no weight at
all. See "The scorer" below and D1's closure in `deferred_decisions.md`.

The honest claim this build supports: **the cost model, the weight-search
protocol, and the abstention band all did exactly what they were built to
do — respond to real measurement, including measurements that overturn a
prior run's conclusion.** Whether the shipped scorer is the right one to ship
is a separate question this run answers less comfortably than the last.

---

## What it writes to `out/`

| File | Contents |
|---|---|
| `transactions.csv` | The transaction stream. **No label columns** — the detector's only input. |
| `labels.csv` | Ground truth, kept separate on purpose. |
| `components.csv` | Every candidate: split, score, and each signal's raw / normalised / detail. |
| `graph_edges.json` | Typed nodes, degrees and edges per component — what the UI draws. |
| `integrity_report.json` | Cardinalities, reuse histograms, class balance, non-triviality panel. |
| `threshold.json` | The binary threshold, F1-selected on validation, frozen before test is read. |
| `weight_policy.json` | The weight search: five candidates, its own cost-selected threshold and held-out read. |
| `abstention_policy.json` | The Allow / Review / Escalate band, and its held-out read. |
| `xgboost_policy.json` | The Tier 2 XGBoost search: four candidates, refusal reasons, no held-out read (no winner). |
| `graphsage_policy.json` | The Tier 3 GraphSAGE search: three candidates, the winner, and its held-out read. |
| `eval_report.json` | Held-out metrics at the frozen `threshold.json` operating point (component + account level). |
| `baselines.json` | The five PRD baselines plus the Tier 2/3 rows, each with its own frozen cutoff or threshold. |
| `ablations.json` | Full model vs. each signal group removed, each with its own frozen threshold. |
| `bootstrap_ci.json` | 95% percentile-bootstrap CIs (5,000 resamples) around the `eval_report.json` point estimates. |

Every file carries the seed, the config fingerprint and the Python version.
`tests/test_riskmesh.py` check 18 regenerates all fourteen and compares byte
for byte.

---

## How the data is built

**Normal behaviour is correlated, not random rows.** Each account has a sticky
merchant set on a popularity power law, its own device and home IP, a personal
amount multiplier, lognormal activity, diurnal timestamps, and a contiguous
activity spell. 20 carrier-NAT IPs are each shared by 158–220 unrelated
accounts — the common infrastructure the graph has to survive.

**Rings (60, five mechanisms, 12 each) share different infrastructure per
type**, so no single graph rule catches all of them:

- **device** — ~68% of traffic through one shared device; either a small
  shared-instrument pool (70% of device rings, "hybrid-funded") or a flat
  2–3-member partial card overlap.
- **ip** — one shared non-common IP (65% share), no device convergence.
- **instrument** — funded through a small shared-instrument pool; no device
  or IP convergence.
- **refund** — elevated refund/failure rate and a concentrated 2-merchant
  pool; a weak partial-instrument overlap gives the graph a structural edge
  to form a component from at all (with no edge at all the ring reduces to
  singletons and is never scored — a defect Task 3 found and fixed).
- **hybrid** — device, IP, *and* instrument pool all at once — the type that
  looks most like every mechanism firing together.

Every ring type bursts with the same probability (`1 - p_ring_no_burst`,
70%); a ring that always does everything is separable by one rule.

**Hard negatives (105, four types, legitimate lookalikes, not more rings):**

- **family (60)** — a household of up to 8 shares a device *and* a home IP
  *and* often a card, with real tenure and diverse merchants. The hard
  negative for `device` and `ip` rings.
- **office (15)** — a corporate shared IP (85%) plus a small shared-device
  pool, long tenure. The hard negative for `device` and `ip` rings from a
  different angle: workplace convergence, not household.
- **hostel (15)** — a shared IP (75%) with individually-owned devices, young
  accounts. The deliberate collision with `ip`-type rings and
  `account_newness`.
- **retail (15)** — genuinely unrelated customers who share a small merchant
  pool and burst together; a weak instrument overlap gives the graph an edge
  to form a component. The hard negative for `refund`-type rings and
  `temporal_burst`/`merchant_concentration`.

**Unlabelled noise matters too.** 175 background account pairs share a device
and 50 share an instrument, with no label at all. Without this, "two accounts
share infrastructure" would separate the classes by construction and the
benchmark would measure nothing.

### Graph hygiene

1. **Merchants never link.** Everyone touches the popular merchants; merchant
   edges would merge the whole population. They stay as evidence only.
2. **Degree cap.** An attribute used by more than `max_ip_degree` (12),
   `max_device_degree` (12) or `max_instrument_degree` (9) distinct accounts is
   common infrastructure and stops linking. Caps sit above the largest legitimate
   ring or hard-negative cluster, so nothing real is capped away.
3. **Minimum edge weight.** An account must use an attribute ≥ 2 times to link
   through it. One incidental touch should not weld two populations together.

Union-find over what survives; components with ≥ 2 accounts become candidates.

---

## The scorer

Weighted sum of eight signals, each with a raw value, a normalised [0,1] value
and a human-readable detail string. Weights sum to exactly 1.00. Current
vector (`experiments/weight_policy.json`, `A_baseline` == the winner of the
current re-freeze, `weight_search_protocol.md` §8):

| Signal | Weight | Measures |
|---|---|---|
| `device_sharing` | 0.3929 | Most accounts on one device |
| `instrument_pool_concentration` | 0.2143 | Accounts funded through one small shared instrument pool |
| `failure_refund_rate` | 0.2143 | Refund + failure rate vs the population baseline |
| `account_newness` | 0.1786 | Inverted median account age |
| `temporal_burst` | **0.00** | Most distinct accounts converging on one merchant in 30 min — see below |
| `ip_sharing` | **0.00** | Most accounts on one non-common IP — see below |
| `instrument_sharing` | **0.00** | Most accounts on one payment instrument — see below |
| `merchant_concentration` | **0.00** | Share of traffic at one merchant — see below |

**Four of the original eight signals now carry zero weight.** Each is a
measured finding, not an oversight:

- `ip_sharing` (RISK-001) — mis-signed from the start: the ring injector's
  own home-IP behaviour used to place no ring information in the IP
  dimension at all, and the original definition counted transactions rather
  than accounts, making it a back-door household detector. Zero since Tier
  0. Now that a real shared-IP ring type exists (Task 3), the ring-vs-all-
  negatives delta reads +0.0200 — essentially flat, no separation either
  way, on the current data (`out/integrity_report.json` ->
  `non_triviality.signal_sign_check`).
- `instrument_sharing` and `merchant_concentration` — zeroed by Phase 11's
  weight search (`D_drop_flagged`, RISK-004/RISK-002), unchanged by the
  current re-freeze.
- `temporal_burst` — zeroed by the **current** re-freeze
  (`E_drop_temporal`, this task's finding #3 above). Separates rings from
  each of the four hard-negative types individually (F1 0.71–0.91 depending
  on type) but not well enough against all four combined for a single
  weight to earn its keep. `deferred_decisions.md` D1 — open since Tier 0 —
  is now closed on this evidence.

**Ring-vs-family is not the same comparison as ring-vs-all-negatives, and
they now disagree for the top-weighted signal — filed as `bugs.md` RISK-005.**
Per hard-negative cluster type, train+validation, `out/components.csv`
(`device_sharing`, ring mean 0.1837 against each type):

| cluster type | n | mean | ring-minus-type delta |
|---|---|---|---|
| family | 40 | 0.3523 | **-0.1686** (badly mis-signed) |
| office | 10 | 0.2636 | **-0.0799** (mis-signed) |
| hostel | 10 | 0.0000 | +0.1837 (fine) |
| retail | 24 | 0.0000 | +0.1837 (fine) |

`device_sharing` — the scorer's single largest weight (0.3929) — is
**negative** against exactly the two hard-negative types deliberately built
to converge on shared devices (family, up to 8 accounts on one device;
office, a shared device pool), because most ring types (`ip`, `instrument`,
`refund`) never touch a shared device at all while both those hard-negative
types do. Against **all** negatives pooled together the delta is positive
(+0.0468, `weighted_contribution` +0.0184), which is what the panel's
`no_weighted_signal_mis_signed` gate checks and why it still passes — the
pooled check dilutes 50 mis-signed components (family + office) against 126
correctly-signed ones (hostel + retail + background) and cannot see the
per-type split. `instrument_pool_concentration` (+0.1150 ring-vs-family) and
`failure_refund_rate` (+0.2654 ring-vs-family) are unambiguously correctly
signed against every hard-negative type; `account_newness` most of all
(+0.6625 ring-vs-family). This is structurally the identical blind spot
RISK-001 (`ip_sharing`) and RISK-004 (`instrument_sharing`) were about — a
signal mis-signed against a specific hard-negative type, masked by an
aggregate check — now found on the scorer's own largest weight, filed in
full as `bugs.md` RISK-005 (open; not fixed here — see the entry for what the
next weight-search or panel-design phase must decide).

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

**Every published metric in this file carries its threshold and how that
threshold was chosen.** Two selection procedures run on this benchmark, at
two different operating points, and they must never be mixed (see the next
section):

- `select_threshold()` picks the threshold that **maximises F1** on
  validation. Frozen to `out/threshold.json`, read back by the runner and
  served by the API.
- `select_weights()` picks the threshold that **minimises expected financial
  loss** on validation, as one output of the weight search. Frozen inside
  `experiments/weight_policy.json`'s own `held_out` block.

Same discipline for the abstention band and every row of the baseline and
ablation tables: each frozen cutoff is selected on validation and the
held-out split is read exactly once.

### The non-triviality panel

Computed on **train + validation only**, because those are the numbers you would
tune the generator against. Six checks, each printed next to its bound:

| Check | Bound | Current |
|---|---|---|
| score distributions overlap | must overlap | True |
| positives below top negative | ≥ 20% | 64.58% |
| hard negative inside positive range | ≥ 1 | 52 |
| no single signal separates perfectly | F1 < 1.0 — **fails the run** | max 0.7957 (`account_newness`) |
| shared-device-only baseline | F1 < 0.85 | 0.4961 |
| no weighted signal mis-signed | flag, not fail | none |

Verdict: **PASS**, with wider margin than any prior phase on every bound
(`out/integrity_report.json`). Max-F1 is swept in **both** threshold
directions (`>= t` and `<= t`) — three signals separate in the inverted
direction, and a one-directional sweep would understate them badly.

---

## Current figures

After `rm -rf out && python -m riskmesh`. Config fingerprint
`fdf4fc217347d36b`, seed 20260824, Python 3.12.10.

**Dataset** — 19,310 transactions, 2,338 accounts, 3,088 devices, 2,429 IPs,
2,192 instruments, 40 merchants. 60 rings (12 of each of 5 types), 105
hard-negative clusters (60 family, 15 office, 15 hostel, 15 retail). 336
candidate components (1,064 singletons dropped), largest 10 accounts (0.4%),
20 NAT IPs capped as common infrastructure. Non-triviality verdict **PASS**;
shared-device-only baseline F1 0.4961.

### Two Tier 1 operating points — read separately, never mixed

The pipeline runs two independent selection procedures against the same
frozen scorer, at two different objectives. Both are real, both are frozen,
and a reader who quotes one model's F1 next to the other model's expected
loss (or vice versa) is comparing two different thresholds, not two models —
this plan shipped that exact bug once, caught in review before merge (see
`graphsage_protocol.md` §8 and the Task 7 coordinator-correction commit).

**A — `out/threshold.json`, F1-selected on validation. This is the pipeline
headline and what the API serves.**

```
threshold 0.22   selection_metric "f1"   selected on validation (F1 0.8333)
```

Held out (112 test components, one read via `evaluate()`):
precision 0.7200, recall 0.7826, **F1 0.7500**, FPR 0.0787, ring recovery
13/20 (65%), confusion tp 18 / fp 7 / tn 82 / fn 5. Account-level: precision
0.6269, recall 0.7568, F1 0.6857, FPR 0.1613 (421 scored accounts).
95%-CI (percentile bootstrap, 5,000 resamples, `out/bootstrap_ci.json`):
F1 [0.5946, 0.8750] (width 0.2804), precision [0.5385, 0.8966], recall
[0.6000, 0.9500], FPR [0.0238, 0.1379]. **These intervals are wide, and
that is the finding, not a defect** — at n=112 test components a one- or
two-component swing in the resample moves the point estimates by roughly
±0.17-0.18; 0.75 should be read as a central estimate, not a precise one.

**B — `experiments/weight_policy.json`'s own `held_out`, cost-selected on
validation via the weight search's expected-loss objective.**

```
threshold 0.10   selected by minimising expected financial loss on validation
```

Held out (same 112 test components, one read via
`evaluate_frozen_policy()`): precision 0.3793, recall 0.9565, **F1 0.5432**,
FPR 0.4045, ring recovery 16/20 (80%), confusion tp 22 / fp 36 / fn 1 / tn 53,
**expected loss 92,263.55** (beats flag-everything's 109,190.85 by 15.5%),
review rate 51.79%. 9 of 36 false positives are background components, not
hard-negative artifacts — the first run where a material share of residual
error isn't a lookalike collision.

**A PRD compliance gap, disclosed rather than fixed.** `PRD.md`'s
"Threshold optimization" Must-have requires the operating threshold be
*"based on expected financial loss rather than maximizing a single ML
metric,"* with the *"selected threshold minimiz[ing] expected validation
loss."* Read A: the threshold the pipeline actually ships and the API
actually serves (0.22) is F1-selected, not loss-selected — the PRD's own
worked example (`PRD.md` line 641: *"We do not choose the threshold that
maximizes F1"*) is not what `out/threshold.json` does. The loss-selected
point exists and is frozen (Read B, threshold 0.10), but it is not what the
pipeline headlines or the API serves. **This is not fixed here.** Switching
`out/threshold.json`'s selection metric would move every headline number in
this file a second time and is scoped work of its own, not a side effect of
a documentation sweep — see the new entry in `deferred_decisions.md`.

### Decision policy — the first genuine, non-degenerate Review band

```
score < 0.10          -> Allow
0.10 <= score < 0.20  -> Review     (deferred to a human, one manual review)
score >= 0.20         -> Escalate
```

Layered on Read B's threshold (0.10). Both boundaries were freely searched
behind a pre-declared 25% review-coverage gate (design review rate 24.11%),
minimised on validation, frozen before test was read. **Every prior run of
this search collapsed to `t_lo == t_hi`**, making the three-way policy
bit-identical to the binary one. This run does not: held out, the three-way
policy reaches expected loss **75,529.35** against the binary policy's
92,263.55 on the identical rows — an **18.1% improvement**, the first
held-out result where Review beats rather than ties the binary policy.
Review absorbs 28 negatives the binary policy would have escalated and
defers 4 positives; escalate-tier FPR drops from 0.4045 to 0.0899.
Mechanism: this run's `C_fn`/`C_fp` ratio (69.9:1) is the least lopsided
this project has derived, giving Review a genuinely closer cost trade-off to
exploit than any prior run's benchmark did.

`deferred_decisions.md` D3 (the review-cost double-charge) remains resolved
as of Phase 10 — one cost model, not two.

### Baselines (each at its own frozen cutoff/threshold, held-out)

| Baseline | Sees graph | Cutoff/threshold | Direction | F1 | FPR |
|---|---|---|---|---|---|
| `random` | none | 0.148688 | ≥ | 0.3252 | 0.8989 |
| `shared_device_only` | one rule | 1 | ≤ | 0.4839 | 0.2697 |
| `shared_ip_only` | one rule | 9 | ≤ | 0.3407 | 1.0000 |
| `transaction_level` | none | 0.697368 | ≥ | **0.7727** | **0.0449** |
| `ring_score` (shipped) | fully | 0.22 | ≥ | 0.7500 | 0.0787 |
| `xgboost_scorer` (Tier 2) | tabular, same 8 signals | — | — | **refused** — no feasible candidate, no held-out read | — |
| `gnn_scorer` (Tier 3) | fully (GraphSAGE) | 0.03 | ≥ | 0.5412 | 0.4382 |

**Do not read `transaction_level` vs `ring_score` off this table alone** —
see finding #1 above for the per-ring-type recall breakdown; the bare F1/FPR
pair here is precision-driven and does not show that the graph recovers more
rings overall. Full field set (descriptions, refusal reasons, validation F1)
in `out/baselines.json`.

### Ablations (leave-one-group-out, each with its own frozen threshold)

| Removed | Threshold | F1 | Δ | Rings found |
|---|---|---|---|---|
| — full model | 0.22 | 0.7500 | — | 13/20 |
| `device` | 0.27 | 0.8696 | **+0.1196** | 14/20 |
| `ip` | 0.22 | 0.7500 | 0.0000 | 13/20 |
| `instrument` | 0.26 | 0.6522 | **-0.0978** | 11/20 |
| `temporal` | 0.22 | 0.7500 | 0.0000 | 13/20 |
| `behavioral_refund` | 0.42 | 0.2308 | **-0.5192** | 3/20 |

See finding #2 above. `ip` and `temporal` tie exactly because both groups
already carry zero weight in the full model — removing a zero changes
nothing.

### Tier 2 — XGBoost scorer

`xgboost_protocol.md`, frozen before any candidate was scored: four
pre-declared `XGBClassifier` configurations over the linear scorer's own 8
signals, fit on train only, gated by the identical panel/difficulty gates
above. **All four refused — but by the opposite mechanism from the prior,
smaller benchmark.** The old ~30-row training split made three of four
candidates degenerate to a constant prediction; the current 124-row training
split is over four times larger and none of the four candidates degenerates
— all four produce dozens of distinct out-of-sample validation predictions
(19, 53, 19, 71). Instead, **all four over-separate**: even the shallowest
candidate (`X1_shallow`) pushes `positives_below_max_negative` to 0.2174,
well under the 0.45 floor. More real training data let every candidate
actually split the classes, and the difficulty gate caught all four for it.
**No candidate reached a held-out read, so XGBoost does not beat Tier 1 —
there is no XGBoost number to compare, not an unfavourable one.** Full
mechanism writeup in `xgboost_protocol.md` §8; frozen record in
`experiments/xgboost_policy.json`.

### Tier 3 (stretch) — GraphSAGE scorer

`graphsage_protocol.md`, frozen before any candidate was scored: three
pre-declared hand-rolled GraphSAGE architectures (plain `torch` tensor ops,
no `torch_geometric`/`dgl`) over structural node features only (one-hot type
+ degree, deliberately not the linear scorer's 8 signals), gated by the
identical three feasibility gates. **All three candidates cleared every
gate this run** — a different outcome from the prior benchmark, where two of
three over-separated. `G2_two_layer` wins on validation expected loss
(51,015.40) and is refit on train+validation for the single held-out read:
precision 0.3710, recall **1.0000**, F1 **0.5412**, FPR 0.4382, ring
recovery 17/20 (85%), **expected loss 54,308.35**, review rate 55.36%.

**At each model's own cost-selected operating point** (Read B above for
Tier 1, `G2_two_layer`'s frozen threshold for Tier 3):

| | threshold | F1 | expected loss |
|---|---|---|---|
| Tier 1 (`weight_policy.json` held_out) | 0.10 | 0.5432 | 92,263.55 |
| Tier 3 (`graphsage_policy.json` held_out, `G2_two_layer`) | 0.03 | 0.5412 | **54,308.35** |

**F1s are effectively tied (0.002 apart); GraphSAGE's expected loss is ~41%
lower — and expected loss is the PRD's own stated primary decision metric**
(`PRD.md`: *"Expected financial loss is the primary decision criterion;
precision, recall, F1, false-positive rate, and ring recovery are supporting
evidence."*). Mechanism: `G2`'s threshold drives recall to 1.0 (misses zero
of 20 test rings) at the cost of FPR 0.4382 — nearly 6x Tier 1's FPR on the
same rows; at this benchmark's 69.9:1 `C_fn`/`C_fp` ratio, expected loss
rewards that trade-off heavily while F1 penalises it symmetrically. This is
not evidence GraphSAGE "generalises better" in general — `A_baseline` shows
the identical recall-heavy shape (0.9565) for the identical structural
reason (dropping `temporal_burst` also pushed its own threshold low).

`graphsage_protocol.md` §8's "beats Tier 1" criterion (held-out F1 **or**
held-out expected loss at least as good) was pre-declared in the *original*
protocol commit `242d078`, months before any candidate was run — the
provenance is verified in git history, so this reads as a pre-registered
criterion the result happened to satisfy on one leg, not one written to fit
the outcome. It is a technically-true, substantively mixed result, and it is
reported that way rather than as an unqualified win. Full mechanism writeup:
`graphsage_protocol.md` §8; frozen record in `experiments/graphsage_policy.json`.

### No comparison mixes an operating point that wasn't its own

Every number in the two tables above and the baseline table came with the
threshold that produced it. `baselines.json`'s `gnn_scorer` row carries a
`tier1_reference` block that is Tier 1's own cost-selected `held_out` (Read
B, 0.10 / 0.5432 / 92,263.55) — never `ring_score`'s F1-selected row (Read A,
0.22 / 0.75) — with a `source` field naming exactly which file it came from,
so a caller of `/benchmark` cannot accidentally pair the two.

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
GET  /threshold-analysis       cost derivation, the expected-loss ladder, and a
                                101-point threshold sweep over the six PRD-named
                                columns (validation only)
GET  /benchmark                integrity panel, baselines (incl. Tier 2/3),
                                ablations, bootstrap CIs
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
| **A shipped GraphSAGE or XGBoost scorer** | Both attempted as their own frozen protocols. XGBoost has no feasible candidate on this benchmark (all four over-separate). GraphSAGE's winner ties Tier 1 on F1 and beats it on expected loss, but that is a mixed, PRD-metric-dependent result, not a clean replacement — see "Current figures". |
| **A loss-selected `out/threshold.json`** | PRD's Must-have asks for the shipped threshold to be expected-loss-selected; the shipped one is F1-selected. Disclosed, not silently fixed — see "Two Tier 1 operating points" above and `deferred_decisions.md`. |
| **A real LLM behind `/explain`** | The grounding contract and fallback are built and demonstrated; the model is the first thing the PRD says to cut. |
| **Auth, a database, deployment** | Explicitly out of scope for the buildathon. |

---

## Project files

```
riskmesh/config.py       every knob + the config fingerprint
riskmesh/generate.py     entities, correlated traffic, five ring + four cluster injectors
riskmesh/graph.py        typed edges, hygiene caps, union-find components
riskmesh/score.py        eight signals, raw + normalised + detail
riskmesh/split.py        chronological ring-level split
riskmesh/integrity.py    integrity report + non-triviality panel
riskmesh/costmodel.py    cost derivation, weight search, feasibility gates
riskmesh/abstention.py   the three-way band search
riskmesh/comparisons.py  the five PRD baselines + the Tier 2/3 rows + the ablation table
riskmesh/evaluate.py     ground-truth rule, threshold freeze, metrics, bootstrap CI
riskmesh/experiment.py   the recorded signal experiments (E1-E6)
riskmesh/ml.py           XGBoost candidates, the same gates reused unchanged
riskmesh/gnn.py          hand-rolled GraphSAGE candidates, the same gates reused unchanged
riskmesh/freeze.py       the one entry point that regenerates all four frozen records
riskmesh/__main__.py     the one command
riskmesh/api/            FastAPI: artifacts, bands, payloads, audit, routes
frontend/                React console (Vite + React 19 + TypeScript +
                          Tailwind v4), the PRD-named client for the four
                          Primary Screens — see frontend/README.md
mockups/                 index.html + four screens (b-mosaic, investigator,
                          threshold-cost, benchmark) + api.js, a
                          dependency-free reference client kept as a
                          lightweight fallback (no 1:1 parity with frontend/
                          required), + five Playwright verify-*.mjs checks
design-api/              earlier canvas-tool design draft for the console API
                          surface; superseded by mockups/, kept for provenance
tests/                   33 pipeline checks + 10 API checks + 4 XGBoost checks
                          + 4 GraphSAGE checks + 1 freeze-regeneration check
```

**Where the reasoning lives.** `implementation_plan.md` is the build log, phase
by phase. `bugs.md` carries every RISK entry with its measurements.
`deferred_decisions.md` lists what was knowingly left, with the cost.
`weight_search_protocol.md`, `abstention_protocol.md`, `xgboost_protocol.md`
and `graphsage_protocol.md` are the four protocols that were frozen to git
*before* their runs — read the predictions, then the results.
