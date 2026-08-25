# RiskMesh — Tier 0 benchmark foundation

Coordinated-abuse-ring detection for the Razorpay AI Buildathon (Track 02).
This is **Tier 0 only**: the synthetic data and evaluation layer that everything
else has to stand on. No API, no UI, no ML.

The goal here is not detection quality. It is a benchmark you can hand a judge
without flinching — one where the data is not trivially separable, labels never
reach the detector, rings never straddle a split, and the threshold was never
fitted on the test set.

## Run it

```bash
python -m riskmesh          # generate -> graph -> score -> split -> evaluate
python tests/test_riskmesh.py   # 19 checks
```

No install step and no dependencies — CPython 3.10+ and the standard library.
`requirements.txt` is deliberately empty; that is what makes "reproducible from
a clean environment" true rather than aspirational.

## What it writes to `out/`

| File | Contents |
|---|---|
| `transactions.csv` | The transaction stream. **No label columns** — this is the detector's only input. |
| `labels.csv` | Ground truth: `account_id, ring_id, cluster_id, active_period`. Kept separate on purpose. |
| `components.csv` | Every candidate component: split, score, and each signal's `_raw`, `_norm` and `_detail`. |
| `integrity_report.json` | Entity counts, reuse histograms, component/ring/cluster distributions, class balance, and the non-triviality panel. |
| `threshold.json` | The operating threshold, selected on validation and frozen **before** test data is read. |
| `eval_report.json` | Held-out metrics at that frozen threshold — component-level primary, account-level secondary. |

## Reading the integrity report

Four numbers tell you whether to believe the benchmark:

1. **`component_hygiene.largest_component_share`** — must stay under 15%. If one
   component swallows the population, "connected component" has stopped meaning
   anything and every downstream metric is noise.
2. **`non_triviality.checks`** — five PASS/FAIL rows, each printed next to its
   bound. This is the panel a judge should read first.
3. **`component_hygiene.capped_nodes`** — how many attributes were ruled common
   infrastructure. Expect all 20 carrier-NAT IPs here; if it is 0, the hygiene
   rules are not firing.
4. **`class_balance`** — positives and negatives per split. All three splits must
   contain rings, families, and unlabelled background.

The panel is computed on **train + validation only**. Those are the numbers you
would tune the generator against, and tuning on test statistics is exactly what
the PRD forbids. Test distributions appear afterwards in `eval_report.json`, as
description, never as an input.

### The non-triviality panel

| Check | Bound | Why it exists |
|---|---|---|
| score distributions overlap | must overlap | Disjoint ranges mean any threshold works. |
| positives below top negative | ≥ 20% | A meaningful share of rings must look ordinary. |
| hard negative in positive range | ≥ 1 | At least one family must genuinely look like a ring. |
| no single signal separates perfectly | F1 < 1.0 | Perfect separation by one raw signal makes the graph decoration. **Fails the run.** |
| shared-device-only baseline | F1 < 0.85 | If one rule matches the scorer, the graph earned nothing. |

A signal reaching F1 in [0.95, 1.0) is **flagged** under `flagged_signals` for
manual investigation, not failed. A signal is allowed to be strong; failing on
strength would just train you to loosen the bound.

Max-F1 is swept in **both threshold directions** (`value >= t` and `value <= t`).
Three signals here separate in the inverted direction (low values indicate
abuse), and a one-directional sweep understates them badly. It would also miss a
signal separating *perfectly* while inverted, which is the exact case the
hard-failure guard exists to catch. Currently flagged: `ip_concentration` at
0.9697, tracked as RISK-001 in `bugs.md`.

## How the data is built

**Normal behaviour is correlated, not random rows.** Each account has a sticky
merchant set drawn on a popularity power law, its own device and home IP, a
personal amount multiplier, lognormal activity, diurnal timestamps, and a
contiguous activity spell. Around 20 carrier-NAT IPs are each shared by 55–89
unrelated accounts — the common infrastructure the graph has to survive.

**Rings (24) share a device.** Members are freshly-registered thin-history
accounts routing ~68% of traffic through a shared device, with partial card
overlap, elevated refunds, and usually a coordinated burst. *Usually* is the
point: 30% of rings never burst, refund rates vary per ring, and members keep
their own traffic. A ring that always does everything is separable by one rule.

**Families (24) are the hard negative.** A household shares a device *and* a
home IP *and* often a card — the same structure a ring shares. What differs is
behaviour: real tenure, activity spread across its period, diverse merchants.
Households run up to 8 accounts, as wide as a ring, which is what keeps the
device-only baseline honest. Some genuinely transact together in one evening.

Unlabelled noise matters too: 70 background account pairs share a device with no
label at all. Without it, "two accounts share a device" separates the classes
perfectly and the benchmark measures nothing.

## Graph hygiene

Three rules, all configurable, all reported:

1. **Merchants never link.** Everyone touches the popular merchants, so merchant
   edges would merge the whole population. Merchants stay as evidence only.
2. **Degree cap.** An attribute used by more than `max_ip_degree` (8),
   `max_device_degree` (12) or `max_instrument_degree` (9) distinct accounts is
   common infrastructure and stops linking. Caps sit above the largest legitimate
   ring or household, so nothing real is capped away.
3. **Minimum edge weight.** An account must use an attribute ≥ 2 times to link
   through it. One incidental touch should not weld two populations together.

Union-find over what survives; components with ≥ 2 accounts become candidates.

## The scorer

Weighted sum of seven signals, each with a raw value, a normalised [0,1] value
and a human-readable detail string. Weights sum to exactly 1.00.

| Signal | Weight | Measures |
|---|---|---|
| `temporal_burst` | 0.278 | Most distinct accounts active in any 30-minute window |
| `device_sharing` | 0.244 | Most accounts on one device |
| `instrument_sharing` | 0.144 | Most accounts on one payment instrument |
| `failure_refund_rate` | 0.133 | Refund + failure rate vs the population baseline |
| `ip_sharing` | 0.00 | Most accounts on one non-common IP (see RISK-001) |
| `account_newness` | 0.111 | Inverted median account age |
| `merchant_concentration` | 0.089 | Share of traffic at one merchant |

`temporal_burst` carries the most weight because it is the signal that separates
a ring from a family sharing the same tablet — the structural signals cannot.

`ip_sharing` carries **zero weight**. It was `ip_concentration`, measuring the
share of traffic on a component's top IP, and it was mis-signed: families ran
0.701 against rings' 0.162, so it pushed legitimate clusters up and rings down.
Investigation (RISK-001, closed) found two causes — the ring injector assigns no
shared IP at all, so Tier 0 carries no ring information in the IP dimension; and
the signal counted transactions rather than accounts, unlike its siblings, which
turned it into a back-door ring detector keyed on the *absence* of a household.
It is now defined as max accounts on one non-common IP and weighted 0.00, kept
computed as evidence and ready for Tier 1's shared-IP ring type. The other six
weights are the Tier 0 ratios renormalised to 1.00.

The panel now carries a `signal_sign_check` computed on the **normalised**
values that actually enter the score. This matters: a raw `<=` direction is not
itself a fault — `account_newness` inverts during normalisation by design and
contributes +0.801, the strongest correct signal. Only the normalised view
distinguishes a correct inversion from a mis-signed one.

## Evaluation protocol

**Tier 0 benchmark ground-truth rule:** a component is positive iff ≥ 50% of its
accounts belong to a single injected ring.

This is a labelling convention *for this benchmark*, not a definition of a risk
ring. Some topologies will not satisfy it — a chain of pairwise-shared
attributes can spread one ring across a component where no single ring holds a
majority, and this rule scores that component negative. That is a **known Tier 0
scope limit, not a bug**: Tier 0 injects only compact shared-device rings, for
which the rule is well behaved. A different topology needs a different rule.

The split is **chronological and ring-level**: train days 0–17, validation
18–23, test 24–29. Labelled components take their split from the generator's
explicit `active_period` — the split is a property of how a cluster was built,
not of the data it happened to emit. Each one's median-timestamp period is then
computed independently and asserted equal; a mismatch fails the run rather than
producing a chronology that is fiction. Unlabelled components use the median.

`select_threshold()` receives validation candidates only — its signature makes
passing test data impossible — and the choice is written to `threshold.json`
before any test data is read. The runner then reads that file back, so the
freeze is load-bearing rather than decorative.

## Reproducibility

Everything derives from one `random.Random(cfg.seed)`, threaded explicitly; the
global `random` module is never touched. Every report carries the seed, a config
fingerprint, and the Python version.

That last one is not decoration. CPython guarantees only that `random()`
reproduces across versions — `shuffle`, `sample` and `gauss` may change. So the
claim is byte-identical output **within one interpreter version**, which is what
check 18 verifies. Anything stronger would be a claim the language does not make.

## Not built (deliberately)

SQLite, FastAPI, the React investigator console, the LLM explanation layer,
XGBoost (Tier 2), GraphSAGE (Tier 3), the false-positive cost model and
expected-loss thresholding, ablations, bootstrap confidence intervals, the full
baseline suite, and the four other ring types and three other hard-negative
types. The PRD's scope kill-switch says Tier 1 does not start until Tier 0
passes its gate.

## Project files

```
riskmesh/config.py     every knob + fingerprint
riskmesh/generate.py   entities, normal traffic, both injectors
riskmesh/graph.py      edges, hygiene, union-find components
riskmesh/score.py      seven signals, raw + normalised
riskmesh/split.py      chronological ring-level split
riskmesh/integrity.py  integrity report + non-triviality panel
riskmesh/evaluate.py   ground-truth rule, threshold freeze, metrics
riskmesh/__main__.py   the one command
tests/test_riskmesh.py 18 checks
```

## Current figures

Read from `out/` after a clean regeneration. Config fingerprint `605e71743ebe6a64`,
seed 20260824, Python 3.12.10:

- 5968 transactions, 789 accounts, 975 devices, 902 IPs, 823 instruments, 40 merchants
- 24 rings and 24 family clusters injected
- 100 candidate components, 402 singletons dropped
- largest component 9 accounts (1.14%), 20 NAT IPs capped
- 8 positive components per split; negatives 30 / 23 / 23
- non-triviality verdict **PASS**, shared-device baseline F1 0.7442, total weighted score separation +0.2652
- flagged: `none` (raw single-signal F1); mis-signed weighted signals ['merchant_concentration'] (RISK-002)
- held out at frozen threshold 0.25: precision 0.6154, recall 1.0, F1 0.7619,
  FPR 0.2174, ring recovery 8/8

Working files: `implementation_plan.md` (phases), `testing.md` (checklist),
`audit.md` (plan-vs-code drift), `bugs.md` (structured bug log).
