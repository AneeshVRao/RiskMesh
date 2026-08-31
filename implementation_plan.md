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

**Design target vs. current frozen benchmark.** The counts above (~600 accounts,
~520 devices, ~40 merchants, ~20 carrier-NAT IPs, 5k transactions) are the Phase
2 design targets, written before non-triviality tuning grew the ring/family
population. The frozen benchmark at config fingerprint `7c1e4fb2b329796c`
(`out/integrity_report.json`) is larger, because `n_accounts=520` is the
*background* population only — ring and family accounts are additional:

| | design target | frozen benchmark |
|---|---|---|
| accounts | ~600 | **789** (520 background + ring/family) |
| devices | ~520 | **976** |
| IPs | — | **906** |
| instruments | — | **823** |
| merchants | ~40 | **40** |
| transactions | 5k ±10% | **5,962** |

Both are correct at once: ~600/~520/5k describes the Phase 2 slice as designed,
789/976/5,962 describes what Phase 3's ring/family injectors and later tuning
(RISK-003's E2, the weight search) actually produced on top of it. Read the
table above for the current numbers; read the prose above it for the reasoning
behind the ratios.

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

**Design target vs. current frozen benchmark.** ~12 rings / ~15 families of
sizes 4–9 / 2–5 was the Phase 3 design target. `n_rings` was raised to 24 (8 per
split — "4 was too coarse to report metrics on", `config.py`) and
`family_size_max` to 8 during Tier 0 tuning; both are config knobs, not
generator-logic changes. The frozen benchmark (`out/integrity_report.json`,
fingerprint `7c1e4fb2b329796c`) has **24 rings** (sizes 4–9, matching the
original range) and **24 family clusters** (sizes 2–8, one size wider than the
2–5 design target). Both numbers are correct at once: the design target
explains the original per-cluster sizing rationale above; 24/24 is what Tier 0's
non-triviality tuning settled on and what every frozen result in this file
reports against.

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
| device_sharing | 0.2444 | max accounts on one device, `(k-1)/(cap-1)` |
| temporal_burst | 0.2778 | max distinct accounts converging on the **same merchant** in a 30-min sliding window |
| instrument_sharing | 0.1444 | max accounts on one instrument |
| failure_refund_rate | 0.1333 | component refund+failure rate vs global base rate, clipped |
| account_newness | 0.1111 | inverted median account tenure at first transaction |
| merchant_concentration | 0.0889 | share of component txns at a single merchant |
| ip_sharing | 0.0000 | max accounts on one non-common IP — zero-weighted, see RISK-001 |

Two of these differ from the original plan. `ip_concentration` was redefined as
`ip_sharing` and zero-weighted when RISK-001 showed it was measuring NAT
plumbing; the remaining six renormalise to 1.00. `temporal_burst` gained the
same-merchant requirement when RISK-003 showed a window-only definition could not
tell a household from a ring — it now carries the largest weight on a premise
that has been measured, ring-minus-family +0.1953, rather than assumed.

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

## Tier 1 — required ablation before any pitch claim

This is a gate, not a nice-to-have. The PRD's ablation requirement asks for
device, IP, instrument, temporal and behavioural signal groups; this is the
temporal instance, and it must exist before the demo asserts anything about
`temporal_burst`.

**Why it is a gate.** The scorer weights `temporal_burst` highest (0.278) on the
premise that it separates a coordinated ring from a family sharing one device.
When RISK-003 was filed that premise was false — ring 0.344 against family 0.352
normalised, a separation of -0.008 against the hard negatives. RISK-003 is now
closed and the premise holds on the design splits: ring 0.2969, family 0.1016,
background 0.0034, **ring-minus-family +0.1953**.

That is a *per-signal mean*, not an ablation. This gate still stands unrun. The
pitch line "temporal concentration is what tells a ring apart from legitimate
shared infrastructure" may not be said until removing the signal is shown to cost
something measurable on hard-negative-only F1 or ring-vs-family separation. A
signal with a healthy mean gap can still be redundant with `device_sharing` or
`account_newness`, and only the ablation distinguishes those cases.

### What to measure

Ring-vs-**family** separation, not ring-vs-background. Separating rings from
ordinary unrelated accounts is the easy half of the problem and every signal
already does it; the benchmark exists to test the hard half.

Evaluate on a **hard-negative-only** view: positives unchanged, negatives
restricted to components carrying a family cluster. Background components are
excluded from the denominator, because their presence is exactly what masked
this in `signal_sign_check`. Report the ordinary full-negative numbers alongside,
so the gap between the two is visible rather than implied.

### Configurations to compare

| Run | Scorer |
|---|---|
| full | all seven signals at current weights |
| ablated: temporal | `temporal_burst` weight 0, remaining six renormalised to 1.00 |
| ablated: instrument | `instrument_sharing` weight 0, remaining six renormalised (RISK-004 is the same class of defect and costs nothing extra to measure here) |
| ablated: both | both zeroed, remaining five renormalised |

Renormalise rather than leaving the weights summing to less than one, so the
comparison isolates the signal's contribution instead of also shifting the
score's overall scale against a fixed threshold.

### Protocol

Unchanged from Tier 0, and non-negotiable: each configuration selects its own
threshold on **validation only**, freezes it to disk, then reads test once. Four
configurations means four independent freezes — reusing one configuration's
threshold on another silently leaks the comparison.

### Report

Write `out/ablation_report.json` and a table in the benchmark view:

- precision, recall, F1, FPR per configuration, on both the hard-negative-only
  and full-negative views
- the ring-minus-family normalised delta per signal, which is the number that
  actually diagnoses the problem
- each configuration's frozen threshold and the split it came from

### Passing condition for the pitch claim

The claim "temporal_burst distinguishes rings from legitimate shared
infrastructure" may be made **only if** removing it produces a material drop in
hard-negative-only F1 or in ring-vs-family separation.

### Result: RUN, and the claim is NOT supported

Measured, record at `experiments/ablation_temporal_burst.json`. Removing
`temporal_burst` (weight 0.2778) and renormalising the remaining six changes
nothing that matters:

| | full | minus temporal_burst | change |
|---|---|---|---|
| design ring - family (total score) | 0.1858 | 0.1822 | **-0.0036** |
| design ring - background | 0.3145 | 0.3226 | +0.0081 |
| validation threshold | 0.23 | 0.26 | +0.03 |
| held-out precision | 0.6667 | 0.6667 | 0.0000 |
| held-out recall | 1.0000 | 1.0000 | 0.0000 |
| held-out F1 | 0.8000 | 0.8000 | **0.0000** |
| held-out FPR | 0.1739 | 0.1739 | 0.0000 |
| hard-negatives-only F1 | 0.8000 | 0.8000 | **0.0000** |

The two scorers flag the **identical set** of 12 held-out components, disagreeing
on only 12 of 465 ranking pairs. The verdict is **redundant**, not "contributes
independently" -- and the threshold-free diagnostic points mildly the other way
still: the best achievable held-out F1 is **higher** without the signal (0.9412
against 0.8889).

So the honest pitch line credits `account_newness` (+0.8819),
`failure_refund_rate` (+0.1383) and `device_sharing` (+0.1136), which measurably
do this work. `temporal_burst` is kept at its current weight because removing it
costs nothing either, and because RISK-003's semantic fix made it *measure* what
its name claims even though the information turns out to be duplicated elsewhere.
Reweighting is a separate decision and belongs with the cost model.

**The weight was NOT changed as a result of this, and that is a logged
decision, not an omission.** `temporal_burst` still carries 0.2778 even though
the ablation shows that weight costs ~0.05 of achievable ceiling F1 (0.9412 ->
0.8889). See `deferred_decisions.md` D1, which the cost-model stage owns. Do not
read the surviving weight as evidence anyone has judged it correct.

**A note on what the ablation does not say.** It shows the signal is redundant
*on this generator, at this scale, with these six companions*. A second ring type
that bursts without sharing devices would likely change that. The claim being
blocked is the general one; the measurement is specific.

Recording the expectation up front is deliberate: it stops the ablation being
read backwards to justify whatever the numbers turn out to be.

## RISK-004 — closed, `instrument_sharing` rejected as a production signal

Filed by the seven-signal audit alongside RISK-003: `instrument_sharing` scored
ring 0.2031 against family **0.2969** on train+validation — a ring-minus-family
delta of **-0.0938** at weight 0.1444, a weighted signal pushing the hard
negatives *toward* the positive band.

Three pre-registered fixes were run and rejected, each frozen before the held-out
split was read. Records in `experiments/`:

| | change | ring-family | outcome |
|---|---|---|---|
| **E4** | ring instrument overlap scales with ring size | -0.0391 | rejected — sign never inverts |
| **E5** | feature normalised by component size | **-0.2263** | rejected — worse, plus 78% background saturation |
| **E6** | rings funded through a card pool, scored as accounts-per-instrument | +0.1576 | rejected — over-separates, panel FAILS |

The zero-weight fallback was then run and **also** rejected: removing the signal
takes `positives_below_max_negative` from 0.5625 to 0.1250 and the panel verdict
to FAIL. Its negative delta is a large part of what holds the hard negatives up.

**Status: closed — rejected as a production scoring signal for the current
benchmark and ring type.** The weight stays at 0.1444 because every alternative
measured worse, and the open weight question is tracked as D2 in
`deferred_decisions.md`.

**Scope caveat, preserved deliberately.** What was rejected is instrument sharing
*as a discriminative signal against a household hard negative, for Tier 0's
single shared-device ring type*. It is **not** a finding that instrument
intelligence is useless for coordinated-abuse detection, and must not be quoted
that way. The reason it cannot work here is a property of the generator: Tier 0's
ring shares one card across a subset of members and its hard negative shares one
card across all of them — two mechanisms differing only in what fraction of a
similarly-sized group shares. E6 is the evidence that a **multi-card ring type**
breaks that symmetry: accounts-per-instrument separated the classes immediately
and in the right direction (family fell to exactly 0.0000). E6 was rejected for
over-separating *this* benchmark, not because the feature failed. A future
funding-network ring type should restart from `experiments/experiment_e6.json`.

Two standing lessons came out of this sequence and are filed separately in
`bugs.md`, because neither is about instruments: **L1** (size-based normalisation
degenerates at small component sizes) and **L2** (held-out F1 is not a safe
objective — see below).

## Tier 1 — cost model and weight selection (DONE)

Protocol frozen in `weight_search_protocol.md` before any candidate was scored;
code in `riskmesh/costmodel.py`; record in `out/weight_policy.json`.

**Five pre-declared candidates, no search space.** A continuous search over seven
weights on 16 design positives would fit noise with no honest way to report how
many configurations were tried. A_baseline (control), B_equal,
C_separation_proportional, D_drop_flagged, E_drop_temporal.

**Three hard feasibility gates, all structural.** `gated_expected_loss()` raises
rather than returning a number, the same way `held_out_view()` raises rather than
returning test rows. An infeasible candidate gets no expected loss at all — not a
number that is later discarded.

| gate | bound |
|---|---|
| non-triviality panel | verdict `PASS` |
| `hard_negatives_inside_positive_range` | `>= 4` |
| `positives_below_max_negative` | `>= 0.45` |

The two difficulty gates were added **before `select_weights()` was implemented**,
for the measured reason recorded as **L2**: held-out F1 rose 0.8000 → 0.8889
twice, by two unrelated mechanisms, and the panel went PASS → FAIL both times. A
higher score on this benchmark can mean a better scorer *or* an easier benchmark
and the metric cannot tell them apart, so difficulty is constrained before
expected loss is allowed to matter. The bounds are absolute rather than a margin
from the incumbent, so a run of individually reasonable changes cannot ratchet
difficulty down one accepted step at a time.

**Costs derived from the dataset** (PRD "Cost Inputs", no round numbers):
`C_review` 500.00 (20 analyst-minutes at INR 1500/hour — the one assumed input),
`C_fn` 74,645.29 (median ring-component exposure), `C_fp` 848.23 (one review plus
2% of median negative exposure).

### Result — A_baseline retained

| policy | panel | pbmn | hard-neg | feasible | threshold | expected loss |
|---|---|---|---|---|---|---|
| **A_baseline** | PASS | 0.5625 | 4 | **yes** | 0.23 | **5,348.23** |
| B_equal | PASS | 0.3125 | 1 | no | — | — |
| C_separation_proportional | FAIL | 0.0000 | 0 | no | — | — |
| D_drop_flagged | FAIL | 0.1250 | 1 | no | — | — |
| E_drop_temporal | PASS | 0.5625 | 4 | yes | 0.26 | 5,348.23 |

Three of five refused. B is the case the tightening was for — it passes the panel
and still loses three of four hard negatives from the positive range. A and E tie
at *exactly* 5,348.23; the tie breaks to A on incumbent-over-change. **Nothing
beat A**, and nothing was relaxed to produce a different winner.

E tying A exactly is the third independent confirmation that `temporal_burst` is
redundant — it changes no held-out metric and no expected-loss figure, only the
threshold that reaches it. This strengthens D1 rather than resolving it.

Sensitivity over `FN_ABSORBED_FRACTION` × `FP_FRICTION_RATE` is stable: A wins all
nine cells. `FN_ABSORBED_FRACTION` has no effect at all, because A's optimum has
**fn = 0** and `C_fn` is multiplied by zero — so the cost model is currently
insensitive to the input it was mainly derived from. Recorded, not glossed.

### The single permitted held-out read

| | validation (selection) | held out |
|---|---|---|
| precision | — | **0.6667** |
| recall | — | **1.0000** |
| F1 | — | **0.8000** |
| FPR | — | **0.1739** |
| ring recovery | — | **8/8 (100%)** |
| confusion | tp 8, fp 1, fn 0, tn 22 | tp 8, **fp 4**, fn 0, tn 19 |
| expected loss | 5,348.23 | **9,392.92** |
| review rate | 0.2903 | 0.3871 |

**The cost gap is the headline, not the F1.** Held-out expected loss is 76%
higher than the figure the policy was selected on — not leakage (the threshold was
frozen first) but small-sample variance, one false positive on 23 validation
negatives against four on 23 test negatives. **The validation expected loss must
not be quoted as the system's cost.**

**All four held-out false positives are family components; none are background.**
The residual error is entirely the hard negatives the benchmark exists to
produce, which argues for the abstention band rather than more weight tuning.

**No further held-out read is permitted under this record.** Same rule already
stated for the ablation: any future comparison — XGBoost included — needs its own
protocol frozen before the read, or the 0.8000 / 9,392.92 baseline stops meaning
anything.

## Tier 1 remaining

What is actually left, so this file can be read top to bottom without the build
history. Everything above this line is done and committed.

**Done:** Tier 0 generator and benchmark (tagged `tier0-baseline`); RISK-001 and
RISK-003 closed (tagged); RISK-004 closed as above; the temporal ablation gate;
the false-positive cost model, expected-loss thresholding and weight selection,
with one held-out read taken; the abstention / review-band policy, with its own
frozen protocol and its own single held-out read (item 1 below).

**Remaining, roughly in order:**

1. ~~**Abstention / manual-review band.**~~ **DONE.** Protocol frozen in
   `abstention_protocol.md` before any band was scored; code in
   `riskmesh/abstention.py`; record in `experiments/abstention_policy.json`.
   Free two-threshold search (`t_lo`, `t_hi` both swept, 0.23 *not* pinned),
   behind a pre-declared `MAX_REVIEW_RATE = 0.25` coverage gate on
   train+validation enforced by `ReviewBandGateFailure`, objective minimised on
   validation only, single held-out read through
   `evaluate_frozen_abstention_policy()`.

   Selected band `t_lo = 0.23`, `t_hi = 0.33`. Held out: expected loss
   **6,000.00** against the binary baseline's 9,392.92 on the identical rows
   (−36.1%, or −18.8% under a D3-corrected cost model — see below), review rate
   19.35%, and **zero escalated false positives** — all four of the binary
   policy's held-out false positives are family components and all four land
   inside the review band, which is exactly what the argument below predicted.
   Escalate-tier precision 1.0000, FPR 0.0000; escalate-tier recall 0.7500 with
   the remaining two rings deferred to review rather than missed, and nothing
   auto-allowed on either split.

   The one new assumption, named as an assumption: a reviewed component is
   resolved correctly, so it costs one review and neither `C_fp` nor `C_fn`.
   That is a Phase-1 cost-model assumption, not an empirical measurement. The
   improvement's *magnitude* is also sensitive to `deferred_decisions.md` D3
   (`C_fp` double-charges a review); its direction and the zero-false-positive
   finding are not.
2. **SQLite persistence and the FastAPI service.** Endpoints over the existing
   artifacts; no modelling change.
3. **React investigator console.** The `detail` strings in `score.py` were built
   for this and are produced by the same computation as the score, so the
   evidence view does not need reconstructing.
4. **LLM explanation layer**, reading those same `detail` strings.
5. **XGBoost (Tier 2)** — and it does **not** start by training a model. It
   starts by freezing a comparison protocol, exactly as the weight search did:
   candidate set, feasibility gates (the same three), what beating the baseline
   means, and a single held-out read. The Tier 1 baseline it must beat is F1
   0.8000 / expected loss 9,392.92 at threshold 0.23. Ring-level splits already
   prevent the obvious leakage; the non-obvious risk is described immediately
   below.
6. **RISK-002** (`merchant_concentration` mis-signed against all negatives:
   delta **-0.0522**, weighted contribution **-0.0046** at weight 0.0889 — see
   `bugs.md`. Ring-minus-**family** alone is the opposite sign, **+0.0103**; the
   two deltas measure different comparisons and neither substitutes for the
   other, per RISK-003's lesson that ring-vs-background can mask ring-vs-family)
   — **stays deprioritised.** It is FLAG-level, the smallest weight in the
   scorer, and the weight search found no feasible candidate that improved on
   leaving it alone.
7. **Additional ring and hard-negative types**, which is also what would let
   RISK-004's instrument work be revisited from E6.

### Why abstention comes before XGBoost

Not a sequencing preference. It follows from what the held-out read actually
said, and from L2.

**Every held-out error is a hard negative.** At the frozen A_baseline policy the
test confusion matrix is tp 8, fp 4, fn 0, tn 19 — and **all four false positives
are family components. Zero are background.** Recall is 1.0000; the scorer misses
nothing. The entire residual error is the legitimate-lookalike class the
generator was built to produce, and those components sit inside the positive
score range on purpose: `hard_negatives_inside_positive_range` is 4, and
`positives_below_max_negative` is 0.5625, both by construction.

**That is the shape of problem abstention solves and discrimination does not.**
A household sharing a device, a card and an evening genuinely resembles a ring on
the features available; the overlap is a property of the data, not a deficiency
of the model. A three-way **allow / review / escalate** policy routes exactly
that ambiguous band to a human, which is the correct handling of a case where the
evidence is genuinely equivocal. A stronger classifier, by contrast, would have to
*out-discriminate* an overlap the benchmark deliberately created — and the four
components it would need to separate are the ones RISK-004 already established
cannot be separated on the instrument dimension for this ring type.

**And pursuing XGBoost next carries a specific risk that abstention does not.** A
supervised model would be trained and evaluated against **this** benchmark — the
one `bugs.md` L2 showed can reward an easier task over a better model. L2's
evidence: held-out F1 rose 0.8000 → 0.8889 twice, by two unrelated mechanisms
(E6's near-separator, and the zero-weight fallback's renormalisation onto
`account_newness`), and the non-triviality panel went PASS → FAIL both times. A
gradient-boosted model has far more capacity to find that kind of solution than a
six-signal linear score does, and it will find it preferentially, because it is
the cheapest way to improve the objective. The three feasibility gates would have
to hold against a model that can fit the difficulty structure itself, which is a
strictly harder guarantee than holding them against five hand-declared weight
vectors.

Abstention changes the **decision policy** over a frozen scorer. It cannot erode
the benchmark, because it does not touch what the scorer computes — so it is
evaluable without re-litigating difficulty. That makes it the lower-risk next
step, and the fact that it is also cheaper is incidental.

None of this says XGBoost should be skipped. It says XGBoost needs its frozen
comparison protocol written *first*, with the same three gates, and that the
abstention band should exist before it so the Tier 2 comparison is against a
system already handling its ambiguous cases properly rather than against one
forced into a binary call.

**Still deferred beyond Tier 1:** GraphSAGE (Tier 3), bootstrap confidence
intervals, the full baseline suite.

**Open decisions carried forward:** D1 and D2 in `deferred_decisions.md`. They are
coupled — removing weight from one signal raises the other's share — and neither
was resolved by the weight search.

---

## Tier 1 — investigator console API (DONE)

The four locked UI mockups needed real data. The API design pass is recorded in
`design-api/` (published canvas); this section records the decisions that
changed the repo.

### The governing rule

**The API never re-scores.** `riskmesh.score` is imported nowhere under
`riskmesh/api/`. `out/components.csv` is the scorer's own output and the API
reads it. A live re-score would let the number on screen drift from the number
in the frozen record, and every other discipline in this project rests on those
being the same number.

Six of the eight PRD endpoints are pure file reads. The API's total arithmetic
is: `contribution = round(w * norm, 6)`, a two-compare band assignment, a sort,
two multiplies for the loss-ladder bounds, and one audit append.

### Dependency decision — FastAPI and uvicorn

`requirements.txt` says not to add a dependency without moving the decision here
first. Doing that now.

**Added:** `fastapi`, `uvicorn`. **Why:** the PRD names FastAPI explicitly in
Technical Specifications, and the console is a graded deliverable.

**What is preserved:** Tier 0's zero-dependency guarantee is intact.
`python -m riskmesh` and `tests/test_riskmesh.py` still import nothing outside
the stdlib, so "reproducible from a clean environment" still holds for the
benchmark itself. The new dependency is confined to the API layer, and within
that layer only `routes.py` and `main.py` touch FastAPI — `artifacts.py`,
`bands.py`, `payloads.py` and `audit.py` are stdlib-only and are tested by
`tests/test_api.py` without a web server running.

### Three new pipeline outputs (6 files -> 9)

- **`out/graph_edges.json`** — account-to-shared-attribute adjacency per
  component, for the UI graph. Built in `__main__.py` rather than live in the
  API so it sits inside the fingerprinted, reproducible pipeline. Written for
  **all** components, not only flagged ones: the restriction saved 112 KB of
  309 KB and would have coupled the file to a threshold, so that a future
  `t_lo` below the binary threshold would 404 on reviewed components.
- **`out/weight_policy.json`** and **`out/abstention_policy.json`** — byte
  copies (`shutil.copyfile`) of the frozen records in `experiments/`, so `out/`
  is the single directory the API reads. `experiments/` is provenance, not a
  runtime source. Never a JSON round-trip: re-serialising could reorder keys and
  break byte-for-byte reproducibility on a file whose content never changed.

  The abstention copy was found by the clean-checkout verification, not by
  design: `out/` is gitignored and `abstention_policy.json` is written by its own
  freeze stage, so after `rm -rf out && python -m riskmesh` the API could not
  start — and its error message told the user to run the very command that had
  just failed to produce the file. A fresh clone plus one command now leaves
  `out/` complete.

All three are covered by `test_18_reproducible_outputs`, which now asserts **9**
files reproduce byte-for-byte at the same seed.

### The weights the API uses are Config's, not weight_policy.json's

Found while implementing, and it matters. `weight_policy.json` rounds its
weights to 4dp for display — A_baseline's sum to **0.9999**, not 1.0. Computing
contributions from that copy drifts from the frozen score by up to **6e-5 on 60
of 100 components**. Small, but it is exactly the "screen disagrees with the
record" failure this design exists to prevent.

`Config().weights` is the authoritative source: it is what `score.py` read, and
it is what `config_fingerprint` is derived from, so the startup fingerprint
assertion already guards it. Importing `Config` is not importing the scorer.
With it, the contribution sum reproduces the frozen score to 6e-17.
`weight_policy.json` remains the provenance record, served verbatim by
`/benchmark`, rounding and all.

### peer_rule — frozen

`nearest_opposite_label_prefer_family`. Same split, opposite label, prefer
`has_family` (the panel is ring vs *household*), minimise score distance,
tiebreak on higher score then lexicographic `component_id`. A documented
heuristic, not a derived optimum. Verified: yields `c_a00533 -> c_a00727`, zero
distance ties on the frozen data, identical across 50 shuffles of input order.
The tiebreaks never fire today and are specified anyway.

### Audit trail — append-only JSONL

`out/audit_log.jsonl`, the only mutable state in the system. Chosen over SQLite:
one writer, append-then-tail-N, a nested evidence snapshot that is already JSON,
and every other artifact here is an inspectable file. Switch to SQLite on any of
— more than one writer process, queries across components, or mutable records.
The whole surface is `append()` and `tail()`, so that swap stays in one file.

`POST /rings/{id}/review` blocks nothing and changes no frozen artifact. The
evidence snapshot is embedded rather than referenced, so the record still says
what the analyst actually saw after the pipeline re-freezes.

**The action bar posts and then re-reads.** A click POSTs, then re-fetches
`/rings/{id}/evidence` and renders the trail from *that* — never from the POST
body and never from optimistic local state. The cost is one extra round trip;
the gain is that a write which did not land cannot look like one that did. The
same rule drives button state: an action already on the server's record for the
component is disabled, so the state survives a reload and is shared between the
Control Center and the Investigator, because neither page owns it. Changing your
mind to a *different* action stays available — recording `allow` over `escalate`
sets `agreed_with_system: false`, which is the disagreement the trail exists to
capture. Verified by `mockups/verify-actions.mjs`, whose negative control aborts
the POST in the browser and asserts the screen refuses to show a record.

### Ring selection and the graph renderer

One function, `selectComponent(id)`, owns everything a component shows. It
fetches `/rings/{id}/evidence` once and redraws the graph, the signal ledger,
the score decomposition, the ring-vs-household comparison, the audit trail and
the action bar from that single response — so no panel can be left holding the
previous component's numbers. The Control Center's queue and the Investigator's
picker both route through it, which is why they cannot disagree about what
"selected" means. The Control Center opens on `rings[0]` rather than a
hardcoded id: `/rings` is ordered by score, so the queue and the detail panel
agree by construction.

The graph is drawn from the `graph` block in that payload — the frozen
`out/graph_edges.json` — in three columns, shared attributes → accounts →
merchants, which is the order the finding is argued in. The layout is
arithmetic, not a force simulation: identical input must give an identical
picture, or the drawing cannot be checked against the API the way every other
number on screen is. `mockups/verify-selection.mjs` does exactly that — it reads
the node ids, degrees and edge count back out of the painted SVG and compares
them to the API's answer for that id, across four components, and its negative
control rewrites a degree in flight to prove the drawing follows the payload.

One honest asymmetry the caption states outright: the graph draws every
attribute shared by two or more accounts, including infrastructure the hygiene
rule caps (`ip_nat*`), while `ip_sharing` skips capped IPs. A household can
therefore show nine IP boxes and still score 6 on that signal. The node count
is structure, not the signal.

### `/explain` — contract only, deliberately not built

Per the PRD's Tier 1 fallback rule this is the first thing to cut. The endpoint
exists and returns the **deterministic** composition of the scorer's own
`detail` strings with `fallback_used: true`. No model is wired.

The grounding contract if it is ever built: the request carries a component id
and no numbers, so a client cannot induce a claim the detector never made; every
numeric token in generated text must appear in the evidence block or the
generation is rejected; the action is never in the model's output path. Honest
limit — that validation cannot catch a fluent misattribution of intent, which is
the real argument for leaving the deterministic path in place.

## PRD rows 63 and 70 — baselines and leave-one-group-out ablation

**Written before any of it was run.** The point of this section existing first is
that the readings below are committed in advance, so whichever way the numbers
land they get reported as-is rather than narrated into whatever supports the
pitch. Same discipline as `experiments/ablation_temporal_burst.json`.

Two PRD acceptance criteria are unmet and this closes both:

- **Row 63** wants at least *random, shared-device-only, shared-IP-only,
  transaction-level and deterministic-ring-score* baselines. What existed was
  `shared_device_only_baseline_f1` plus per-signal best-achievable F1 — two of
  the five, and both as *ceilings* on design data rather than frozen held-out
  reads, so they were not comparable with the headline 0.8000.
- **Row 70** wants *full model vs. each feature group removed*. What existed was
  `single_signal_max_f1` — each signal **alone**, which is the inverse of an
  ablation — plus two drop-group weight candidates inside the weight search,
  which is a selection procedure, not a reported ablation table.

### The protocol, identical for every row in both tables

Unchanged from Tier 0 and non-negotiable: **each configuration selects its own
cutoff on validation only, freezes it, and then reads test exactly once.** Twelve
configurations means twelve independent freezes. Reusing one configuration's
threshold on another silently leaks the comparison — that is the whole reason
`select_threshold()` takes validation candidates as its entire input.

The two tables freeze to `out/baselines.json` and `out/ablations.json`, both
carrying `config_fingerprint`, both added to `test_18`'s byte-for-byte list
(9 files → 11) and to the API's one-run assertion.

### Row 63 — the five baselines

| Baseline | Score per component | Sees the graph? |
|---|---|---|
| `random` | `Random(f"{seed}:{component_id}").random()` | no |
| `shared_device_only` | raw `device_sharing` — accounts on the most-shared device | one rule from it |
| `shared_ip_only` | raw `ip_sharing` — accounts on the most-shared non-common IP | one rule from it |
| `transaction_level` | fraction of the component's transactions a naive per-transaction rule flags | **no** |
| `ring_score` | the shipped weighted score | yes, fully |

`random` is keyed on the component id rather than drawn from a stream, so it does
not depend on iteration order and reproduces byte-for-byte like everything else.

`transaction_level` is the control that matters most, because it is the one a
reviewer will ask about: *would a transaction-level model have found these
anyway?* It flags a transaction when it is a refund or a failure, or its amount
is at/above the 95th percentile, or the account is 30 days old or younger — raw
fields on the transaction itself, no shared-attribute counts, no component
structure beyond which transactions are being averaged. **The amount percentile
is computed on train+validation transactions only**; computing it over the whole
stream would leak the test split's amount distribution into the baseline.

**Cutoffs are swept in both directions.** Not a refinement — RISK-001 is exactly
the bug where a `>=`-only sweep reported an inverted signal as useless.
`ip_sharing` is inverted in this benchmark (rings keep separate IPs, households
share the router), so a one-directional sweep would report the shared-IP baseline
as far weaker than it honestly is. The direction is chosen on validation with the
cutoff, frozen with it, and applied to test as frozen. This makes every baseline
*stronger*, which is the conservative direction for a claim of the form "the
system beats these".

### Row 70 — the five ablation groups

The PRD names device, IP, instrument, temporal and behavioural/refund. Mapped
onto the seven signals as a **partition** — every signal belongs to exactly one
group, so "full minus each group in turn" covers the whole scorer and no signal
is silently ablated twice or never:

| Group | Signals removed |
|---|---|
| `device` | `device_sharing` |
| `ip` | `ip_sharing` |
| `instrument` | `instrument_sharing` |
| `temporal` | `temporal_burst` |
| `behavioral_refund` | `failure_refund_rate`, `account_newness`, `merchant_concentration` |

The three-signal behavioural group is a grouping choice and is called one: the
split is structural (what accounts *share*) against behavioural (how accounts
*act*). Merchant concentration sits on the behavioural side because it describes
where the money went, not what two accounts have in common.

Weights are **renormalised** after zeroing, exactly as in the temporal ablation,
for the reason recorded there: holding the survivors fixed and letting the total
fall below 1.0 multiplies every score by a constant, which is a change of units
measured against a fixed threshold, not an ablation.

Ablated scorers are weighted sums on the same [0, 1] scale and in the same
orientation as the shipped model, so they use `select_threshold()` itself — the
audited function — rather than the baselines' value sweep. "Same protocol as the
main model" is then literally true rather than approximately true.

### Committed in advance

*Expected:* `ring_score` beats `random` by a wide margin; `transaction_level`
lands well below it, because the thesis of the whole project is that coordination
is visible in aggregate and not in any single transaction; `shared_device_only`
lands close behind the full model, since one rule already reaches 0.7442
achievable F1 on design data.

*Predicted no-op:* the `ip` ablation must come out **exactly identical** to the
full model, because RISK-001 already set `ip_sharing`'s weight to 0.0 and
renormalising a zero changes nothing. If it differs at all, that is a
renormalisation bug to fix, not a result to report.

*The readings that would be uncomfortable, and are reported anyway:*

- If `shared_device_only` **matches or beats** the full model on held-out F1, the
  graph score is not earning its complexity on this benchmark and the pitch may
  not claim it does. `max_shared_device_baseline_f1` is already a hard gate on
  design data; this would be the held-out counterpart.
- If any ablation **improves** held-out F1, the shipped weight vector is not the
  best one available. It gets reported plainly.

**What will not happen either way: no weight, threshold or band is re-selected on
the basis of these held-out reads.** That is the leakage this project spent its
whole protocol preventing, and twelve fresh test reads is precisely the situation
where it would be tempting. These tables are a report. Any change they argue for
is a design decision that must be made on design splits, in a separate run, with
its own freeze.

### Result — RUN, and both uncomfortable readings fired

Records at `out/baselines.json` and `out/ablations.json`, both in the
byte-for-byte reproducibility test. The protocol section above was committed
before any of this ran; nothing below was re-selected on the strength of it.

**The prediction held.** Ablating `ip` came out byte-identical to the full model,
as predicted, because RISK-001 had already zeroed that weight. `test_22` now
asserts it rather than admiring it.

#### Row 63 — the graph score does not win its own baseline table

| Baseline | Sees graph | Frozen cutoff | Held-out F1 | FPR | Hard-neg F1 |
|---|---|---|---|---|---|
| `transaction_level` | none | ≥ 1.0 | **1.0000** | 0.0000 | 1.0000 |
| `ring_score` | fully | ≥ 0.23 | 0.8000 | 0.1739 | 0.8000 |
| `shared_device_only` | one rule | ≥ 4 | 0.6957 | 0.3043 | 0.6957 |
| `shared_ip_only` | one rule | ≤ 1 | 0.5161 | 0.6522 | **1.0000** |
| `random` | none | ≥ 0.3718 | 0.2857 | 0.6957 | 0.4706 |

A transaction-level rule that never touches the graph separates the held-out
split **perfectly**. One clause carries it: every ring transaction in the test
split comes from an account **≤ 25 days** old, while negatives run to a median of
**316**. No negative component is made entirely of young accounts, so
"all transactions from accounts ≤ 30d" is an exact classifier.

The 30-day cut was fixed in the protocol above before the run, and it is not a
tuned constant — validation F1 is 1.0000 for every cut from 20 to 180 days, and
only falls (0.8571) at 10. The record carries that sweep.

**This is a statement about the benchmark, not about graph detection.** The
non-triviality panel came within 0.0088 of catching it: `account_newness` alone
scores 0.9412 against a 0.95 bound, and passed. Aggregating the same field per
*transaction* rather than per component clears the bound outright. The gate was
one aggregation away from firing, which is the most useful thing this table says.

`shared_ip_only` reaching 1.0000 on the hard-negative view is the RISK-001 story
told from the other end: sweeping both directions, "at most one account per IP"
separates ring from household perfectly, because households share a router and
rings do not. It is useless as a detector — 0.6522 FPR against the full negative
set — and it is exactly why the direction sweep is not optional.

**The shipped scorer is reported at its own frozen threshold**, not re-swept over
observed values like the four challengers. The finer sweep would have scored it
0.8421; it ships at 0.8000 and that is the number the table carries, because the
Benchmark tab may not show two different held-out F1s for one detector. Holding
the incumbent to the coarser grid while the challengers get the finer one errs
against the incumbent, which is the safe direction here. `test_24` pins it.

#### Row 70 — one group of five is load-bearing

| Removed | Weight | Threshold | Held-out F1 | Δ | Rings | Hard-neg F1 |
|---|---|---|---|---|---|---|
| — full model | — | 0.23 | 0.8000 | — | 8/8 | 0.8000 |
| `behavioral_refund` | 0.3333 | 0.22 | 0.6316 | **−0.1684** | **6/8** | 0.6316 |
| `device` | 0.2444 | 0.18 | 0.8000 | 0.0000 | 8/8 | 0.8000 |
| `ip` | 0.0000 | 0.23 | 0.8000 | 0.0000 | 8/8 | 0.8000 |
| `temporal` | 0.2778 | 0.26 | 0.8000 | 0.0000 | 8/8 | 0.8000 |
| `instrument` | 0.1444 | 0.25 | 0.8889 | **+0.0889** | 8/8 | 0.8889 |

Only the behavioural and refund group costs anything: 0.1684 F1 and two of eight
rings. The three *structural* groups — device, IP, instrument — are the ones the
graph exists to compute, and removing them costs **nothing or less than nothing**.
Removing `instrument_sharing` improves held-out F1 to 0.8889 and halves FPR,
consistent with RISK-004 having already filed that signal as defective and with
the weight gate refusing `D_drop_flagged`.

Held against the temporal ablation recorded earlier in this document, the
`temporal` row reproduces it exactly (0.8000 → 0.8000), which is a useful
consistency check on the new code path — as is `test_21`, which asserts the
`full` row equals `eval_report.json` cell for cell.

**No weight was changed on the strength of any of this.** Six fresh held-out
reads is precisely the situation the protocol above anticipated. Re-weighting
because an ablation looked good on test is selection on a held-out read; if the
`instrument` result is to be acted on, it belongs in a weight search on design
splits with its own freeze, which is where `D_drop_flagged` already lives.

#### What the two tables say together

They agree, and the agreement is not flattering. The baselines say a non-graph
rule wins outright; the ablation says the graph-structural signals are the ones
that can be removed for free. Both point at the same cause: **this generator
makes ring accounts uniformly young, and account age is doing the work the graph
is credited with.** That is rows 56/58/59 — a second ring type whose accounts are
not uniformly young — and it is deliberately not attempted this close to the
deadline, because it re-fingerprints every number in the build.

The honest claim the demo can make is the narrow one: on this benchmark, the
three-way abstention policy and the cost model are what earn their keep, and the
graph score is not yet shown to beat a simple attribute rule. Saying more than
that requires the generator work.

---

## Phase 10-11 — the account-age confound fix, and the re-freeze it forced

**Phase 10's target was stated by the previous section, not invented here:**
"a second ring type whose accounts are not uniformly young... deliberately not
attempted this close to the deadline, because it re-fingerprints every number
in the build." Phase 10 did exactly that — a hybrid pool-funded ring mechanism
(a configurable fraction of rings, tuned to 0.7, fund every member through a
small shared-instrument pool instead of personal cards, **and** draw signup
age from a much wider range, `ring_hybrid_signup_min_days`=5 to
`ring_hybrid_signup_max_days`=400, instead of the uniformly-young default) —
plus the 8th signal, `instrument_pool_concentration`, that scores the new
mechanism, and the D3 cost-model fix (`deferred_decisions.md` D3, closed).

**Phase 10 stopped short of re-running the weight search and abstention
protocols on purpose**, because both are supposed to select on a benchmark
that is already final, and the generator was still moving. Phase 11 is that
re-run: `weight_search_protocol.md` and `abstention_protocol.md` frozen and
executed against the settled Phase 10 benchmark, `experiments/weight_policy.json`
and `experiments/abstention_policy.json` re-frozen with the current config
fingerprint, and every document that quoted a number from either protocol
updated to match. Full results are in those two files; this section reports
the one finding the whole two-phase effort exists to produce.

### The actual target: does `transaction_level` still reach F1 1.0000 on held-out?

**No.** Re-running `comparisons.baseline_report()` fresh from `out/baselines.json`
on the Phase 10/11 benchmark:

| Baseline | Sees graph | Frozen cutoff | Held-out F1 | FPR | Hard-neg F1 |
|---|---|---|---|---|---|
| `ring_score` | fully | ≥ 0.23 | **0.8750** | 0.0417 | 0.8750 |
| `transaction_level` | none | ≥ 5,715.91 | **0.7143** | 0.0417 | 0.7143 |
| `shared_device_only` | one rule | ≥ 4 | 0.6957 | 0.2917 | 0.6957 |
| `shared_ip_only` | one rule | ≥ 1 | 0.5000 | 0.6667 | 0.5000 |
| `random` | none | ≥ 0.084563 | 0.2000 | 0.0417 | 0.4706 |

`transaction_level` — precision 0.8333, recall 0.6250, tp 5 / fp 1 / tn 23 /
fn 3 — no longer separates the held-out split perfectly, and the shipped
`ring_score` (F1 0.8750) now **beats** it outright, reversing finding #1 from
the pre-Phase-10 README. The age-cut sensitivity sweep, re-run on validation,
confirms the mechanism rather than merely the headline: F1 is no longer flat
at 1.0000 across every cut from 20 to 180 days (the old confound's signature)
— it now varies (0.7059 at 10 days, 0.6667 flat from 20-60, falling to 0.6154
at 90) because a hybrid ring's members are a mix of fresh mules and older
compromised/synthetic accounts, so "account age ≤ N days" is no longer close
to a perfect ring classifier at any cut.

**This is the honest result, reported whichever way it landed, per this
document's own committed-in-advance framing for the original row 63/70 run.**
It is not a clean sweep: `transaction_level` (0.7143) still beats
`shared_device_only` (0.6957) and `shared_ip_only` (0.5000), so a naive
per-transaction rule remains a stronger baseline than two of the graph's own
one-rule challengers. What changed is specifically the comparison the whole
phase was aimed at — the graph score against the strongest non-graph
baseline — and on that comparison the graph score now wins.

### Row 70 — the ablation table, re-run

| Removed | Weight | Threshold | Held-out F1 | Δ | Rings | Hard-neg F1 |
|---|---|---|---|---|---|---|
| — full model | — | 0.23 | 0.8750 | — | 7/8 | 0.8750 |
| `behavioral_refund` | 0.2716 | 0.23 | 0.7059 | **−0.1691** | 6/8 | 0.7059 |
| `device` | 0.2716 | 0.16 | 0.9333 | **+0.0583** | 7/8 | 0.9333 |
| `ip` | 0.0000 | 0.23 | 0.8750 | 0.0000 | 7/8 | 0.8750 |
| `instrument` | 0.1481 | 0.26 | 0.7778 | **−0.0972** | 7/8 | 0.7778 |
| `temporal` | 0.3086 | 0.25 | 0.8421 | −0.0329 | 8/8 | 0.8421 |

**A new reading this table did not have before: removing `device` improves
held-out F1**, not just `instrument` as in the original run. This is reported
plainly, on the same "no weight is changed on the strength of a held-out
ablation" rule the original row 70 section already committed to — any
reweighting this suggests belongs in a future weight-search re-run with its
own freeze, not a same-phase reaction to this table. `ip` again reproduces the
full model exactly, as it must while `ip_sharing` carries weight 0.00.

### What this does and does not settle

The graph score beating `transaction_level` on this specific benchmark draw is
not proof the graph is generally better — it is proof that the account-age
confound this build named as its central limitation is no longer forcing the
comparison, on this generator, this seed. `shared_device_only` and
`shared_ip_only` still trail badly, which keeps the original caution alive in
weaker form: a full graph is not yet shown to beat *every* simpler rule, only
the one the previous phase's finding #1 was about. The honest headline moves
from "a non-graph rule beats the graph score" to "the graph score beats the
strongest non-graph rule tried, on the axis this phase targeted" — narrower
than a general claim, and that narrowness is deliberate.
