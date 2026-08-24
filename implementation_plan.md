# RiskMesh Tier 0 — phased implementation plan

## Context

`D:\Projects\ML\riskmesh` holds only `PRD.md`. This builds the PRD's **Initial
Development Slice** (§Synthetic Data Design): one shared-device ring type, one
family hard negative, a relationship graph, a deterministic scorer, a
chronological ring-level split, and an evaluation runner.

The goal of Tier 0 is **not detection quality**. It is a benchmark you can defend
to a judge. The things that kill this kind of submission are all data-layer
failures: synthetic data that is trivially separable, labels leaking into
features, rings leaking across splits, a threshold fitted on the test set, and
one giant graph component that makes "connected component" meaningless. Every
phase below closes one of those.

**Out of scope, deliberately:** UI, FastAPI, SQLite, LLM layer, XGBoost, GNN,
cost model, ablations, and any additional ring or hard-negative type. The PRD's
scope kill-switch says not to start Tier 1 until Tier 0 passes its gate.

## Decisions already taken

- **Stdlib only** — `random`, `csv`, `json`, `collections`, `statistics`,
  `dataclasses`. Union-find is ~15 lines and beats adding networkx; CSVs are
  pandas-readable when Tier 2 needs them. Zero dependencies makes "reproducible
  from a clean environment" (a graded PRD criterion) trivially true.
  `requirements.txt` stays empty for Tier 0.
- **Eval unit: component primary, account secondary** — `eval_report.json` has a
  `primary` block (unit=component) and a `secondary` block (unit=account).
  Headline numbers use component-level.
- **Threshold selected on validation by F1, persisted to disk before test is
  touched.** Expected-cost thresholding is Tier 1.
- **Scale:** 600 accounts / 30 days / ~5k transactions. Runs in seconds.
- **CSV files in `out/` are the database** at this scale. SQLite arrives with the
  API in Tier 1.
- **Tier 0 time cap: ~25% of total available build time for Phases 0–5.** At that
  checkpoint, if the non-triviality panel is not yet inside its bounds, **tune the
  existing config knobs first** — ring/cluster ratios, sizes, noise rates — rather
  than adding new generator realism or new signals. A config change is reversible
  in minutes; a design change is not. Reaching for more realism when the numbers
  look wrong is the specific way Tier 0 eats a hackathon.
- **Budget for the rest:** ~40% of total build time for the complete Tier 1
  baseline, ~20% for Tier 2, ~15% for final integration and demo freeze.

## How to use this plan

Work one phase at a time, in order. Each phase lists the files it creates, the
steps, and a **Done when** check you can actually run. Do not start a phase until
the previous phase's check passes — several later phases assert things earlier
phases are responsible for producing, so an unnoticed gap surfaces as a confusing
failure three phases later.

### The six guardrail files

These markdown files are the guardrails that keep an AI assistant from drifting or
hallucinating across sessions. They live in the project root alongside the code.

| File | Role | Lifetime |
|---|---|---|
| `PRD.md` | Defines the app, audience, MVP scope, and what **not** to build. Read at the start of every session. | Permanent — already written |
| `implementation_plan.md` | This document. Phased, checkbox-based build plan generated from the PRD. Work one phase at a time; never "build the whole app." | Permanent, checkboxes tick as you go |
| `audit.md` | Forces a comparison of what was actually built against the plan — gaps, mistakes, orphaned files. | Overwritten after each major phase |
| `task_today.md` | A scoped task file for the next couple of hours only. | Deleted after each feature, to keep context clean |
| `bugs.md` | Structured bug reports — what happens, the error, files involved — so a fix is reasoned about before code is touched. | Appended as bugs appear, entries cleared when fixed |
| `testing.md` | Checklist of test cases to verify or script before merging any feature. | Permanent, grows per phase |

Note the repo's file is `PRD.md` (uppercase) — that is the one to read; don't
create a second lowercase `prd.md`.

### The per-phase ritual

Same four beats every phase — the ritual is what makes the guardrails work:

1. **Start** — write `task_today.md` scoped to *this phase only*: the goal, the
   files it touches, the Done-when check. Nothing from later phases goes in it.
2. **Build** — work only what `task_today.md` names. If something breaks, write a
   structured entry in `bugs.md` (symptom, exact error, files involved, suspected
   cause) and reason about the fix *before* editing code.
3. **Verify** — run the phase's rows in `testing.md`. A phase is not finished
   because the code runs; it is finished when its checklist passes.
4. **Close** — write `audit.md` answering:

   > Analyze the current codebase. Compare what is actually built against
   > `implementation_plan.md`. What is missing? What was built wrong? Are there
   > any orphaned files?

   Then tick the phase's checkboxes here and **delete `task_today.md`**.

`audit.md` is overwritten each time, with the phase number and date at the top. It
is a checkpoint, not a changelog — its job is catching drift between plan and code
while the drift is still only one phase wide. Phases 3, 5, 8, and 9 are the major
checkpoints; the ritual is worth doing at every phase, but those four are
non-negotiable.

---

## Phase 0 — Project setup

**Files:** `riskmesh/__init__.py`, `requirements.txt`, `.gitignore`,
`implementation_plan.md`, `testing.md`, `bugs.md`, `out/` (dir)

- [x] Confirm Python ≥3.10: `python --version`
- [x] Create package folder `riskmesh/` with an empty `__init__.py`
- [x] Empty `requirements.txt` with a one-line comment saying Tier 0 has no
      dependencies on purpose
- [x] `.gitignore`: `out/`, `__pycache__/`, `*.pyc`, `task_today.md`
- [x] `git init` — the PRD asks for a reproducible repo
- [x] Save this document as `implementation_plan.md`
- [x] Create `testing.md` with the section headings for phases 1–9
- [x] Create `bugs.md` with just the entry template

`task_today.md` is *not* created here — it is created at the start of each phase
and deleted at the end, which is what keeps it short-lived. It is gitignored for
the same reason.

**Done when:** `python -c "import riskmesh"` prints nothing and exits 0, and the
four guardrail files exist alongside `PRD.md`.

---

## Phase 1 — Config and seed

**Files:** `riskmesh/config.py`

One frozen `@dataclass Config` holding every knob in the system:

- `seed = 20260824`
- entity counts (accounts, devices, merchants, NAT IPs), `days = 30`
- split boundaries (`train_days=18`, `val_days=6`, `test_days=6`)
- graph hygiene caps: `max_ip_degree=8`, `max_device_degree=12`, `min_edge_txns=2`
- the seven scorer weights
- non-triviality bounds: `min_positive_below_max_negative_fraction=0.20`,
  `max_shared_device_baseline_f1=0.85`, `single_signal_flag_f1=0.95`

Add `fingerprint()` returning a sha256 over the dataclass fields. It goes into
every report, so a set of numbers is always traceable to the exact configuration
that produced it.

Nothing anywhere else in the codebase reads a module-level constant — everything
takes a `Config`. That is what makes a parameter sweep possible later without a
refactor.

**Done when:**
- [x] `assert abs(sum(weights.values()) - 1.0) < 1e-9` passes
- [x] `fingerprint()` returns the same value on two calls

---

## Phase 2 — Entities and normal traffic

**Files:** `riskmesh/generate.py` (first half)

All randomness comes from a single `random.Random(cfg.seed)` passed explicitly.
Never touch the global `random` module — that is the most common way a
"reproducible" generator silently stops being reproducible.

**Entities:** ~600 accounts with signup times spread across the window (giving
real tenure variation), ~520 devices, instruments mostly 1:1 with accounts, ~40
merchants drawn on a popularity power-law with categories, and two IP pools —
per-account residential IPs plus ~20 carrier-NAT IPs each shared by 50–200
accounts. The NAT pool is deliberate: it is the "common infrastructure" that
Phase 4's hygiene rules have to survive.

**Correlated behavior** (the PRD's "not independent random rows"): per-account
activity rate is lognormal; device choice 90% home / 10% secondary; IP choice 70%
home / 25% carrier-NAT / 5% travel; merchant choice sticky (80% from a per-account
preferred set of 3–6, drawn by popularity); amounts lognormal by merchant category
with a per-account multiplier; timestamps follow a diurnal hour-of-day weighting;
~2% refunds and ~4% failures.

**Background noise matters:** a small number of devices and instruments are shared
by 2 accounts with **no label at all**. Without this, "shared device" alone
separates the classes perfectly and the whole benchmark is worthless.

**Done when:**
- [x] 5k ±10% transactions generated
- [x] accounts-per-device is mostly 1 with a thin tail (`Counter` check)
- [x] carrier-NAT IPs show 50+ accounts each

---

## Phase 3 — Ring and family injectors

**Files:** `riskmesh/generate.py` (second half)

**Ring injector — shared device only.** ~12 rings of 4–9 accounts, members freshly
signed up with thin history (realistic mule accounts). One or two shared devices
carry ~85% of ring traffic — *not 100%*, members keep some own-device activity.
Partial instrument overlap across 2–3 members, elevated refund/failure rate, and a
coordinated burst where members hit the same merchant inside a short window. Ring
members also emit ordinary background traffic.

**Family injector — the hard negative.** ~15 clusters of 2–5 accounts sharing a
household device **and** a home IP **and** sometimes a family instrument — the
*same structural attributes as a ring*, which is what makes it a genuine hard
negative rather than an easy one. They differ only behaviorally: long tenure,
activity spread evenly across the window, diverse merchants, baseline refund rate,
no burst. This is what forces the scorer onto temporal and behavioral signals
instead of learning "shared device = fraud".

**Period confinement.** Each ring and each family cluster gets an `active_period`
(train/val/test) at generation time, and all its coordinated activity is placed
inside that period's date range. This is what makes the Phase 6 ring-level split
*possible* rather than best-effort.

**Label separation.** `generate()` returns `(transactions, labels)` as two
separate lists. `transactions.csv` carries no `ring_id`, `cluster_id`, or `is_*`
column. `labels.csv` holds `account_id, ring_id, cluster_id, active_period`.
Only `split.py`, `integrity.py`, and `evaluate.py` ever read labels.

**Done when:**
- [x] every ring's and cluster's coordinated activity falls inside one period
- [x] `transactions.csv` header contains no label column
- [x] `labels.csv` written separately with ring/cluster/period

**→ Checkpoint:** run the phase 2–3 rows in `testing.md`, write `audit.md`
(Phase 3 — data layer done), delete `task_today.md`.

---

## Phase 4 — Graph and connected-component hygiene

**Files:** `riskmesh/graph.py`

Nodes: `account:*`, `device:*`, `ip:*`, `instrument:*`. Edges come from
transaction co-occurrence, weighted by count.

Three documented hygiene rules, all configurable:

1. **Merchants never link.** Every account touches popular merchants, so merchant
   edges would merge the entire population into one component. Merchants stay in
   the graph as evidence/attributes but are excluded from component formation.
2. **Degree cap.** An attribute node used by more than `max_ip_degree` (8) or
   `max_device_degree` (12) distinct accounts is flagged **common infrastructure**
   and stops linking. Carrier-NAT IPs get capped out. The caps sit well above
   realistic ring size (≤9) so a real ring is never capped away, and every capped
   node is listed in the integrity report so the effect stays auditable.
3. **Minimum edge weight.** An account–attribute edge only links if the account
   used that attribute at least `min_edge_txns` (2) times, so one incidental touch
   never merges two populations.

Union-find over the surviving edges. Components with ≥2 accounts become scoring
candidates; singletons are dropped.

**Done when:**
- [x] largest component holds <15% of accounts
- [x] every carrier-NAT IP is flagged common infrastructure
- [x] capped nodes are recorded for the integrity report

---

## Phase 5 — Deterministic scorer

**Files:** `riskmesh/score.py`

Seven signals. Each is computed as a **raw** value and a **normalized** [0,1]
value; the score is the weighted sum of the normalized values, clipped to [0,1].
Weights live in `config.py` and sum to exactly 1.00:

| Signal | w | Definition |
|---|---|---|
| device_sharing | 0.22 | max accounts on one device, `(k-1)/(cap-1)` |
| temporal_burst | 0.25 | max distinct accounts transacting in a 30-min sliding window / component accounts |
| instrument_sharing | 0.13 | max accounts on one instrument |
| failure_refund_rate | 0.12 | component refund+failure rate vs global base rate, clipped |
| ip_concentration | 0.10 | share of component txns on its top non-common IP |
| account_newness | 0.10 | inverted median account tenure at first transaction |
| merchant_concentration | 0.08 | share of component txns at a single merchant |

`temporal_burst` carries the largest weight precisely because it is the signal
that separates a ring from a family sharing the same device.

**Raw + normalized output.** `score_component()` returns
`{score, signals: {name: {raw, normalized, weight, contribution, detail}}}`, where
`detail` is a human-readable rendering — `temporal_burst` carries
`raw=(8, 9, 30)`, `detail="8/9 accounts in 30 minutes"`, `normalized=0.89`. The
evidence string a Tier 1 investigator view or LLM explanation needs is produced
here, not reconstructed later from a bare float. `components.csv` gets both
`<signal>_raw` and `<signal>_norm` columns.

Every signal is a pure function of transactions + graph. `score_component()` takes
no label argument at all, which Phase 9 asserts.

**Done when:**
- [x] weights sum to 1.0
- [x] every signal returns `raw`, `normalized`, `weight`, `contribution`, `detail`
- [x] scoring the same component twice gives an identical result
- [x] `score_component()` takes no label argument

**→ Checkpoint:** run the phase 4–5 rows in `testing.md`, write `audit.md`
(Phase 5 — detector done), delete `task_today.md`.

---

## Phase 6 — Chronological ring-level split

**Files:** `riskmesh/split.py`

Split by date: train = days 0–17, val = 18–23, test = 24–29 (60/20/20), ordered
strictly train → validation → test, boundaries recorded in both reports.

Assignment is **dual-path**:

- **Labeled components** (carrying a ring or family cluster) take their split from
  the generator's explicit `active_period`. That is authoritative — the split is a
  property of how the cluster was constructed, not something inferred from the
  data it emitted.
- The component's **median-timestamp period is computed independently**, and
  `assert active_period == median_timestamp_period` for every labeled component. A
  mismatch means the generator leaked coordinated activity outside its assigned
  period, and the run fails rather than quietly producing a split whose chronology
  is fiction.
- **Unlabeled background components** have no `active_period`, so they keep
  median-timestamp assignment.

Then assert loudly: no `ring_id` appears in two splits, and no `cluster_id`
appears in two splits.

**Done when:**
- [x] `active_period == median_timestamp_period` for every labeled component
- [x] no ring or cluster spans two splits
- [x] all three splits contain at least one ring

---

## Phase 7 — Integrity report

**Files:** `riskmesh/integrity.py`

Prints and writes `out/integrity_report.json`: seed and config fingerprint; entity
cardinalities and transaction count; reuse histograms (accounts-per-device, per-IP,
per-instrument); component-size distribution with explicit giant-component count
and largest-component share; capped-node counts by type; ring count and size
distribution; family-cluster count and size distribution; class balance per split;
temporal coverage per split; and the **non-triviality panel**.

**The non-triviality panel** is the part a judge should read first:

- per-feature raw mean±sd and min/max for positive vs negative components;
- score-distribution overlap — the two ranges and the size of their intersection;
- fraction of positives scoring below the highest-scoring negative;
- per-signal max F1, with any signal in [0.95, 1.0) listed under an explicit
  `flagged_signals` key for manual investigation;
- highest score reached by a hard-negative family component;
- the shared-device-only baseline's precision/recall/F1;
- `ground_truth_rule` — the string naming the Tier 0 labeling convention.

Each line prints next to the bound it must satisfy, so a benchmark that has
drifted into being too easy is visible in the report itself, not only in a failing
test.

**Computed on train + validation components only.** These are exactly the numbers
you would tune the generator against, and the PRD forbids using test statistics to
tune generator parameters. Test-split distributions are reported afterwards in
`eval_report.json` as after-the-fact description — never as an input to a
generator or threshold decision.

**Done when:**
- [x] `out/integrity_report.json` writes and prints
- [x] every non-triviality line sits inside its bound, or is explicitly flagged
- [x] the panel is computed on train+val components only

---

## Phase 8 — Evaluation runner

**Files:** `riskmesh/evaluate.py`, `riskmesh/__main__.py`

**Tier 0 benchmark ground-truth rule:** a component is labeled positive iff ≥50%
of its accounts belong to a single injected ring.

This is a *labeling convention for this benchmark*, not a definition of what a risk
ring is, and it is named that way in the code comment above the function, in the
README, and as a `ground_truth_rule` field in the integrity report. Real ring
topologies exist that it will not capture — a chain of pairwise-shared attributes
can spread a ring across a large component in which no single ring holds a
majority, and this rule scores that component negative. That is a **known Tier 0
scope limit, not a bug**: Tier 0 injects only compact shared-device rings, for
which the rule is well behaved. Stating the limit here is what stops a later
reader mistaking a convention for a claim.

`select_threshold(val_components)` sweeps 0.00–1.00 in 0.01 steps and returns the
best-F1 threshold. It receives **only** validation components. The chosen value is
**persisted to `out/threshold.json`** (threshold, selection metric, validation
component count, seed, config fingerprint) *before any test data is touched*.
`evaluate(test_components, threshold)` reads that frozen value back. Passing test
data to the selector is structurally impossible through the public API; the
persisted file is what makes the freeze auditable after the fact.

`out/eval_report.json`:
- `primary` — unit=component: precision, recall, F1, FPR, TP/FP/TN/FN, ring
  recovery rate (fraction of test rings with a detected component covering ≥50% of
  members)
- `secondary` — unit=account: same metrics, each account inheriting its
  component's score
- `threshold`, `threshold_selected_on: "validation"`, `split_boundaries`, `seed`,
  `config_fingerprint`, `ground_truth_rule`

`__main__.py` wires it: generate → graph → score → split → integrity → threshold on
val → evaluate on test. Writes `out/transactions.csv`, `out/labels.csv`,
`out/components.csv`, `out/integrity_report.json`, `out/threshold.json`,
`out/eval_report.json`, and prints the integrity report and eval summary.

**Done when:**
- [x] `python -m riskmesh` runs end to end
- [x] all six files written to `out/`
- [x] `out/threshold.json` is written before test data is read

**→ Checkpoint:** run the phase 6–8 rows in `testing.md`, write `audit.md`
(Phase 8 — pipeline runs end to end), delete `task_today.md`.

---

## Phase 9 — Tests and README

**Files:** `tests/test_riskmesh.py`, `testing.md` (completed), `README.md`

`testing.md` and `tests/test_riskmesh.py` are two views of the same list:
`testing.md` is the human checklist you tick before merging a feature,
`test_riskmesh.py` is the scripted version of every row that can be automated. A
row lands in `testing.md` when its phase defines it; this phase is where the
script catches up to the full list. Any row that can't be scripted stays in
`testing.md` marked **manual**.

Assert-based, no framework, runnable as `python tests/test_riskmesh.py`.

**Correctness**

1. **Determinism** — two full runs at the same seed produce byte-identical
   `transactions.csv` (compare sha256).
2. **No label leakage** — `transactions.csv` header has no ring/cluster/label
   column; signal names are disjoint from label field names.
3. **Split isolation** — no ring or cluster spans two splits.
4. **Split assignment agrees** — for every labeled component,
   `active_period == median_timestamp_period`.
5. **Hygiene works** — largest component <15% of accounts; every carrier-NAT IP
   flagged as common infrastructure.
6. **Hard negatives are hard** — every family cluster shares ≥1 attribute type
   with at least one ring pattern.

**Non-triviality** (train+val only; bounds from `config.py`)

7. Positive and negative **score distributions overlap**.
8. **≥ `min_positive_below_max_negative_fraction` (0.20) of positives score below
   the highest-scoring negative** — a meaningful fraction, not just one component.
9. **At least one hard-negative family component lands inside the positive score
   range** — a legitimate cluster genuinely looks like a ring.
10. **Single-signal separation is graded, not binary.** Per raw signal, max F1 over
    all thresholds: `== 1.0` **fails the run**; `0.95 ≤ F1 < 1.0` is **flagged in
    the integrity report for manual investigation** and the run continues; below
    0.95 is normal.
11. **Shared-device-only baseline is not near-perfect** — F1 below
    `max_shared_device_baseline_f1` (0.85), a hard failure.

**Pipeline verification**

12. The validation-selected threshold is **persisted** to `out/threshold.json`.
13. Test evaluation **uses exactly that frozen value**, read back from the file.
14. The threshold reported in `eval_report.json` **equals** the validation
    threshold.
15. `TP + FP + TN + FN == len(test_components)` — no component silently dropped.
16. The test split contains **≥1 positive ring component**.
17. The test split contains **≥1 hard-negative or background negative component**.
18. **Two full runs at the same seed reproduce every output file** byte-for-byte.

**README** — how to run (one command, no install step), what each output file
contains, and which integrity numbers to check to confirm the benchmark is honest.
Plus the scorer weights table, the three hygiene rules, and a short section
stating the Tier 0 ground-truth rule with its known topology limit.

**→ Checkpoint:** run the whole of `testing.md`, write `audit.md` (Phase 9 —
Tier 0 complete), delete `task_today.md`.

---

## Verification

```
python tests/test_riskmesh.py     # all 18 assertions pass
python -m riskmesh                # writes out/, prints both reports
```

Then work `testing.md` top to bottom, including the manual rows.

Tier 0 is done when every `testing.md` row passes, the final `audit.md` reports no
gaps and no orphaned files, and `bugs.md` has no open entries.

## Deferred to Tier 1 and beyond

Not built here, listed so the omission is explicit: SQLite persistence, FastAPI
service and its endpoints, the React investigator console, the LLM explanation
layer, XGBoost (Tier 2), GraphSAGE (Tier 3), the false-positive cost model and
expected-loss thresholding, ablation analysis, bootstrap confidence intervals, the
full baseline suite, and the four remaining ring types and three remaining
hard-negative types.
