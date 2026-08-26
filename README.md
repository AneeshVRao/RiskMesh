# RiskMesh -- Tier 0 benchmark foundation

Coordinated-abuse-ring detection for the Razorpay AI Buildathon (Track 02).
This is **Tier 0 only**: the synthetic data and evaluation layer that everything
else has to stand on. No API, no UI, no ML.

The goal here is not detection quality. It is a benchmark you can hand a judge
without flinching -- one where the data is not trivially separable, labels never
reach the detector, rings never straddle a split, and the threshold was never
fitted on the test set.

## Run it

```bash
python -m riskmesh          # generate -> graph -> score -> split -> evaluate
python tests/test_riskmesh.py   # 19 checks
```

No install step and no dependencies -- CPython 3.10+ and the standard library.
`requirements.txt` is deliberately empty; that is what makes "reproducible from
a clean environment" true rather than aspirational.

## Known limitation: ~42% of the scorer's weight is not yet earning it

Stated here rather than left to be discovered. The scorer puts 0.278 on
`temporal_burst` and 0.144 on `instrument_sharing` -- 0.422 of its total weight,
roughly 42%. Measured on held-out data, **neither of those two signals separates
abuse rings from the family hard negatives**, which is the distinction this
benchmark exists to test. On normalised values, `temporal_burst` runs ring 0.297
against family 0.297 -- dead level after its RISK-003 redefinition, improved from
0.344 vs 0.352 but still no separation -- and `instrument_sharing` runs ring 0.203
against family 0.297, where the legitimate clusters score clearly higher. Both signals do separate rings from ordinary background accounts, which is
the easy half of the problem and not the half that matters. The three signals
carrying the real work are `account_newness` (ring-minus-family +0.882),
`failure_refund_rate` (+0.139) and `device_sharing` (+0.114).

The causes are understood and are not mysterious. `temporal_burst` was
neutralised by Tier 0's own generator tuning: closing the non-triviality bounds
required households to burst in the same 30-minute window as rings, which is
honest data at the cost of that signal. Redefining it to require same-merchant
convergence fixed its semantics and removed a traffic-volume bias, but could not
restore separation, because both bursts are emitted by one shared code path
(RISK-003, still open). `instrument_sharing` is
skewed by asymmetric injectors -- ring card overlap is pinned at 2–3 accounts
while a household of up to 8 shares one card, so the normalisation rewards the
family (RISK-004).

Both are **deferred, not fixed**, and deliberately so: correcting either means
changing weights or the ring injector, and both would invalidate the
`tier0-baseline` comparison that the RISK-001 result rests on. They are scheduled
against Tier 1's cost-model and ring-type work, where the trade-offs can be made
once rather than twice. Until the ablation specified in `implementation_plan.md`
has been run, **no pitch or demo should claim `temporal_burst` is what
distinguishes rings from legitimate shared infrastructure** -- the held-out data
does not currently support that claim. Full detail in `bugs.md`.

## What it writes to `out/`

| File | Contents |
|---|---|
| `transactions.csv` | The transaction stream. **No label columns** -- this is the detector's only input. |
| `labels.csv` | Ground truth: `account_id, ring_id, cluster_id, active_period`. Kept separate on purpose. |
| `components.csv` | Every candidate component: split, score, and each signal's `_raw`, `_norm` and `_detail`. |
| `integrity_report.json` | Entity counts, reuse histograms, component/ring/cluster distributions, class balance, and the non-triviality panel. |
| `threshold.json` | The operating threshold, selected on validation and frozen **before** test data is read. |
| `eval_report.json` | Held-out metrics at that frozen threshold -- component-level primary, account-level secondary. |

## Reading the integrity report

Four numbers tell you whether to believe the benchmark:

1. **`component_hygiene.largest_component_share`** -- must stay under 15%. If one
   component swallows the population, "connected component" has stopped meaning
   anything and every downstream metric is noise.
2. **`non_triviality.checks`** -- five PASS/FAIL rows, each printed next to its
   bound. This is the panel a judge should read first.
3. **`component_hygiene.capped_nodes`** -- how many attributes were ruled common
   infrastructure. Expect all 20 carrier-NAT IPs here; if it is 0, the hygiene
   rules are not firing.
4. **`class_balance`** -- positives and negatives per split. All three splits must
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
unrelated accounts -- the common infrastructure the graph has to survive.

**Rings (24) share a device.** Members are freshly-registered thin-history
accounts routing ~68% of traffic through a shared device, with partial card
overlap, elevated refunds, and usually a coordinated burst. *Usually* is the
point: 30% of rings never burst, refund rates vary per ring, and members keep
their own traffic. A ring that always does everything is separable by one rule.

**Families (24) are the hard negative.** A household shares a device *and* a
home IP *and* often a card -- the same structure a ring shares. What differs is
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

`temporal_burst` carries the most weight because coordination in time was
expected to separate a ring from a family sharing the same tablet. It does not:
measured on train+validation it runs ring 0.344 against family **0.352**, so it
separates rings from background and not from the hard negatives. The weight is
unchanged pending **RISK-003**; the claim is corrected rather than left standing.

Only three signals actually separate rings from the family hard negatives --
`account_newness` (+0.882), `failure_refund_rate` (+0.139) and `device_sharing`
(+0.114). About half the scorer's weight sits on signals that do the easy half of
the job (rings vs background) and not the hard half. That is the honest state of
the Tier 1 baseline, and it is what the cost-model and reweighting work has to
address.

`ip_sharing` carries **zero weight**. It was `ip_concentration`, measuring the
share of traffic on a component's top IP, and it was mis-signed: families ran
0.701 against rings' 0.162, so it pushed legitimate clusters up and rings down.
Investigation (RISK-001, closed) found two causes -- the ring injector assigns no
shared IP at all, so Tier 0 carries no ring information in the IP dimension; and
the signal counted transactions rather than accounts, unlike its siblings, which
turned it into a back-door ring detector keyed on the *absence* of a household.
It is now defined as max accounts on one non-common IP and weighted 0.00, kept
computed as evidence and ready for Tier 1's shared-IP ring type. The other six
weights are the Tier 0 ratios renormalised to 1.00.

The panel now carries a `signal_sign_check` computed on the **normalised**
values that actually enter the score. This matters: a raw `<=` direction is not
itself a fault -- `account_newness` inverts during normalisation by design and
contributes +0.801, the strongest correct signal. Only the normalised view
distinguishes a correct inversion from a mis-signed one.

## Evaluation protocol

**Tier 0 benchmark ground-truth rule:** a component is positive iff ≥ 50% of its
accounts belong to a single injected ring.

This is a labelling convention *for this benchmark*, not a definition of a risk
ring. Some topologies will not satisfy it -- a chain of pairwise-shared
attributes can spread one ring across a component where no single ring holds a
majority, and this rule scores that component negative. That is a **known Tier 0
scope limit, not a bug**: Tier 0 injects only compact shared-device rings, for
which the rule is well behaved. A different topology needs a different rule.

The split is **chronological and ring-level**: train days 0–17, validation
18–23, test 24–29. Labelled components take their split from the generator's
explicit `active_period` -- the split is a property of how a cluster was built,
not of the data it happened to emit. Each one's median-timestamp period is then
computed independently and asserted equal; a mismatch fails the run rather than
producing a chronology that is fiction. Unlabelled components use the median.

`select_threshold()` receives validation candidates only -- its signature makes
passing test data impossible -- and the choice is written to `threshold.json`
before any test data is read. The runner then reads that file back, so the
freeze is load-bearing rather than decorative.

## Reproducibility

Everything derives from one `random.Random(cfg.seed)`, threaded explicitly; the
global `random` module is never touched. Every report carries the seed, a config
fingerprint, and the Python version.

That last one is not decoration. CPython guarantees only that `random()`
reproduces across versions -- `shuffle`, `sample` and `gauss` may change. So the
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
tests/test_riskmesh.py 20 checks
```

## Current figures

Read from `out/` after `rm -rf out` and a clean regeneration. Config fingerprint
`7c1e4fb2b329796c`, seed 20260824, Python 3.12.10:

- 5962 transactions, 789 accounts, 976 devices, 906 IPs, 823 instruments, 40 merchants
- 24 rings and 24 family clusters injected
- 100 candidate components, 402 singletons dropped
- largest component 9 accounts (1.14%), 20 NAT IPs capped
- 8 positive components per split; negatives 30 / 23 / 23
- non-triviality verdict **PASS**, shared-device baseline F1 0.7442, total weighted score separation +0.2756
- positives below the top negative 0.5625; 4 hard negatives inside the positive range
- ring-minus-family on `temporal_burst` **+0.1953** (ring 0.2969, family 0.1016, background 0.0034) -- RISK-003 resolved, E2 adopted
- `none` flagged in [0.95, 1.0) (raw single-signal F1); mis-signed weighted signals ['merchant_concentration'] (RISK-002)
- held out at frozen threshold 0.23: precision 0.6667, recall 1.0, F1 0.800,
  FPR 0.1739, ring recovery 8/8

### Operating point (Tier 1 weight selection, closed)

Weight policy `A_baseline` retained after five pre-declared candidates were run
behind three hard feasibility gates; three were refused, and the two that were
feasible tied exactly. Frozen record: `out/weight_policy.json`, protocol in
`weight_search_protocol.md`.

Held out at the frozen threshold 0.23, one read: precision 0.6667, recall 1.0000,
F1 0.8000, FPR 0.1739, ring recovery 8/8, **expected loss 9,392.92** at a 38.71%
review rate. All four false positives are family components, none background.
Validation expected loss was 5,348.23; the held-out figure is 76% higher and is
the one to quote.

**How to describe this result:** we established an explicit cost model and
selected among integrity-valid policies under it; in this benchmark, the final
operating point was dominated by the observed error structure. Not "optimized
to minimize the cost of missed fraud" — A's loss-minimising point has fn = 0,
so `C_fn` is multiplied by zero and never enters the total (`weight_search_protocol.md`
§8). The cost model is real and the gate structure did real work (three of five
candidates refused), but the false-negative cost it was mainly derived from
currently contributes nothing to why A won.

Working files: `implementation_plan.md` (phases), `testing.md` (checklist),
`deferred_decisions.md` (knowingly-deferred decisions and who owns each),
`weight_search_protocol.md` (frozen, run, closed),
`audit.md` (plan-vs-code drift), `bugs.md` (structured bug log).
