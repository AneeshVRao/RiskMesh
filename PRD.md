# Product Requirements Document: RiskMesh

## Product Overview

**Product Vision:** Give payment platforms an AI risk system that detects coordinated abuse rings — not isolated suspicious transactions — by modeling relationships between accounts, devices, IPs, and payment instruments, and by explicitly pricing the financial cost of getting a call wrong.

**Track:** Razorpay Buildathon — Track 02: AI Risk Manager

**Product Type:** Defense-only AI risk intelligence and investigation system.

**Target Users:** Primary — Razorpay's risk/trust & safety team and merchants who need fraud-ring visibility. Secondary — a fraud analyst persona who reviews and acts on flagged rings.

**Business Objectives:** Demonstrate a working, defensible detection system for Razorpay's Track 02 buildathon bar: honest precision/recall on a held-out set, explicit false-positive cost accounting, and a defense-only scope (no offense-capable output).

**Core Product Thesis:** Coordinated abuse is often visible in the relationships between otherwise normal-looking entities. The system should identify suspicious structures while distinguishing them from legitimate shared infrastructure such as families, offices, hostels, and retail networks.

**Success Metrics:**

**Primary decision metric**
- Expected financial loss at the chosen operating threshold, evaluated under the documented cost model.

**Supporting metrics**
- Precision and recall on held-out (unseen) rings
- False-positive rate at the chosen operating threshold
- Ring recovery rate (% of injected rings correctly surfaced)
- Performance against simple baseline detectors
- Performance change under feature ablation
- Confidence intervals for key evaluation metrics where sample size permits
- Reproducibility of the final benchmark from a clean environment
- Demo clarity: can a judge understand *why* a ring was flagged within 10 seconds of looking at the UI

---

## User Personas

### Persona 1: Fraud Analyst (primary)

- **Demographics:** Risk-ops employee at a payments company, moderate technical proficiency, works in a queue-driven review tool daily.
- **Goals:** Find coordinated abuse fast, avoid wasting review time on false alarms, be able to justify an escalation decision to a manager or auditor.
- **Pain Points:** Transaction-level fraud tools miss coordinated abuse spread across many "individually normal-looking" accounts. Alert fatigue from high false-positive tools.
- **User Journey:** Opens Risk Control Center → sees ranked list of detected rings → clicks a ring → reads the relationship graph and the plain-language explanation → chooses Allow / Watch / Manual Review / Escalate.

### Persona 2: Buildathon Judge (secondary, but decisive for this project)

- **Demographics:** Razorpay technical evaluator, high technical proficiency, evaluating in a 5-minute pitch window.
- **Goals:** Assess whether the team can build a real, evaluable AI system — not just an LLM wrapper.
- **Pain Points:** Sees many "fraud detector" submissions with fabricated or trivially-separable data and no honest metrics.
- **User Journey:** Watches the demo → checks whether metrics are on a held-out set → checks whether false positives are priced, not just minimized → inspects whether the synthetic data and evaluation protocol avoid leakage → decides if this is hire-worthy engineering.

---

## Feature Requirements

| Feature | Description | User Stories | Priority | Acceptance Criteria | Dependencies |
|---|---|---|---|---|---|
| **Synthetic transaction + entity generator** | Generates realistic accounts, devices, IPs, payment instruments, merchants, and transactions with normal correlated behavior | As a builder, I want realistic base data so the detector isn't tested against trivial noise | Must-have | Produces 10k+ transactions with plausible device/IP reuse patterns, realistic temporal behavior, and configurable generation parameters | None |
| **Synthetic data integrity and validation layer** | Validates that the generated benchmark is non-trivial, reproducible, and internally consistent | As a judge, I want evidence that benchmark quality is controlled rather than assumed | Must-have | Fixed random seed; entity-cardinality report; reuse distributions; connected-component distributions; class balance; temporal coverage; hard-negative statistics; no detector-derived labels | Synthetic generator |
| **Ring injector** | Injects shared-device, shared-IP, shared-instrument, refund-abuse, and hybrid rings into the base population | As a builder, I need labeled ground truth to evaluate detection | Must-have | Each ring type has configurable size/count; ring membership is stored as independent ground truth; injected rings overlap with normal behavior on some individual signals | Synthetic generator |
| **Hard-negative injector** | Injects legitimate lookalike clusters (family, office, hostel Wi-Fi, retail chain) that share attributes without being abuse | As an analyst, I don't want legitimate shared-IP groups flagged as fraud | Must-have | At least 4 distinct benign cluster types present at realistic scale; hard negatives can share one or more attributes with true rings | Synthetic generator |
| **Relationship graph builder** | Constructs the heterogeneous graph (account-device-IP-instrument-merchant edges) from transaction data | As the system, I need a graph structure to run connected-component and scoring logic on | Must-have | Graph correctly reflects all entity relationships; verified against known injected rings and known legitimate clusters | Generator + injector |
| **Connected-component hygiene** | Prevents common infrastructure from creating meaningless giant graph components | As a builder, I want graph structure to reflect meaningful relationships rather than global connectivity artifacts | Must-have | Common IPs/devices do not automatically merge unrelated populations; configurable frequency caps or edge-weighting rules documented | Graph builder |
| **Deterministic ring risk score (Tier 1 baseline)** | Weighted score from shared-device/IP/instrument density, temporal burst, refund pattern, and other documented signals | As an analyst, I want an interpretable first-pass score before ML is involved | Must-have | Produces a 0-1 risk score per candidate component; weights documented; score is reproducible | Relationship graph |
| **Baseline sanity checks** | Compares RiskMesh against simple and intentionally weak baselines | As a judge, I want evidence that performance comes from coordinated signals rather than a single shortcut | Must-have | Reports at least random, shared-device-only, shared-IP-only, simple transaction-level, and deterministic ring-score baselines | Evaluation pipeline |
| **Ring-level train/test split** | Splits whole rings and relevant legitimate clusters, not individual transactions, to avoid structural leakage | As a judge, I need to trust that the evaluation isn't leaking test information | Must-have | No ring's transactions appear in more than one split; hard-negative clusters remain isolated where applicable | Ring injector |
| **Leakage-safe evaluation protocol** | Controls threshold fitting, feature selection, tuning, and temporal leakage | As a judge, I want to know that the test set was not used to tune the system | Must-have | Threshold chosen using validation only; test set evaluated after threshold freeze; no test statistics used for tuning; exact split strategy and seed reported | Ring-level split |
| **Precision/recall/FP-rate evaluation** | Computes standard classification metrics on the held-out ring set | As a judge, I want honest, standard metrics I can sanity-check | Must-have | Metrics computed only on held-out split; threshold explicitly reported | Leakage-safe evaluation |
| **Metric uncertainty analysis** | Estimates confidence intervals for key metrics where sample size permits | As a judge, I want to know whether reported performance is robust | Should-have | Bootstrap confidence intervals reported for precision, recall, F1, and false-positive rate when statistically meaningful | Evaluation pipeline |
| **False-positive cost model** | Assigns FP/FN/manual-review costs derived from dataset exposure and computes expected cost per threshold | As an analyst, I want to pick a threshold based on financial impact, not abstract F1 | Must-have | Costs are traceable to dataset-derived financial exposure; at least 3 threshold rows shown; selected operating point determined on validation data | Evaluation pipeline |
| **Threshold optimization** | Selects an operating threshold based on expected financial loss rather than maximizing a single ML metric | As a risk manager, I want a business-aware operating point | Must-have | Multiple thresholds compared; selected threshold minimizes expected validation loss under documented cost assumptions; held-out test results then reported | Cost model |
| **Ablation analysis** | Removes individual signal groups to determine their contribution | As a judge, I want evidence that the detector is not driven by one trivial feature | Must-have | Reports full model vs. feature-group ablations for device, IP, instrument, temporal, and behavioral/refund signals | Baseline scorer |
| **XGBoost supervised scorer (Tier 2)** | Trained on engineered graph/behavioral features to improve on the deterministic baseline | As the system, I want a stronger scorer once the baseline is proven correct | Should-have | Outperforms Tier 1 baseline on held-out F1 or expected cost without ring-level leakage; comparison is documented | Tier 1 baseline working end-to-end |
| **Investigator console UI** | Dashboard showing summary stats, ranked rings, graph visualization, explanation panel, and review actions | As an analyst, I want one screen to review and act on a flagged ring | Must-have | Clicking a ring shows its graph, contributing signals, and an Allow/Watch/Manual Review/Escalate action; no automatic blocking | Risk score, graph builder |
| **Abstention / manual-review state** | Allows the system to defer ambiguous cases instead of forcing a binary decision | As an analyst, I want uncertain cases routed to human review | Must-have | Medium-confidence or high-cost-uncertainty cases can be marked Manual Review; abstention policy documented | Threshold analysis |
| **LLM explanation layer** | Generates a plain-language explanation of *why* a ring was flagged, using deterministic/ML signals as input — not as the detector itself | As an analyst, I want a readable summary instead of raw feature dumps | Should-have | Explanation references only actual contributing signals; no hallucinated figures; detector output unchanged if LLM is unavailable | Risk score, graph data |
| **LLM grounding contract** | Restricts the LLM to structured system-generated evidence | As a judge, I want the generative layer separated from authoritative detection logic | Must-have | LLM cannot change risk score, invent unseen values, create new detection decisions, or override detector evidence; deterministic fallback available | LLM explanation layer |
| **GraphSAGE / GNN scorer (Tier 3, stretch)** | Graph neural network as an optional second-stage scorer | As a judge, I want to see technical depth beyond XGBoost if time allows | Could-have | Only attempted after Tiers 1–2 and UI are stable; clearly framed as experimental; benchmark comparison included | Tier 2 complete and stable |
| **Reproducible benchmark runner** | Recreates the final dataset, model, metrics, and tables from source | As a judge/developer, I want reproducible final numbers | Must-have | One documented command/configuration reproduces final benchmark with fixed seed and version metadata | Generator + evaluation pipeline |

---

## Synthetic Data Design

The synthetic dataset is a core product component, not merely a fixture.

### Design Principles

- Generate realistic correlated behavior rather than independent random rows.
- Create legitimate and abusive populations that overlap on individual signals.
- Separate **ground-truth generation** from **detector scoring logic**.
- Include temporal structure so coordinated bursts can be represented.
- Prevent common infrastructure from automatically merging unrelated entities.
- Preserve complete provenance for every injected ring and hard-negative cluster.
- Make generation deterministic using a fixed random seed.
- Ensure that metrics cannot be made artificially strong simply by making abuse behavior trivially separable.

### Initial Development Slice

The first end-to-end benchmark should contain:

1. One shared-device abuse-ring mechanism.
2. One legitimate family-style hard negative.
3. Base transaction generation.
4. Graph construction.
5. Deterministic risk scoring.
6. Ring-level evaluation.

Only after this slice passes end-to-end should additional ring types and hard negatives be introduced.

### Ring Types

The full benchmark should support:

- Shared-device ring
- Shared-IP ring
- Shared-payment-instrument ring
- Refund-abuse ring
- Hybrid multi-attribute ring

### Hard Negative Types

The benchmark should support:

- Family cluster
- Office/shared corporate network
- Hostel/shared Wi-Fi
- Retail-chain/customer convergence

### Data Integrity Checks

Before every benchmark run, report:

- Entity cardinalities
- Attribute reuse distributions
- Connected-component size distribution
- Ring-size distribution
- Legitimate-cluster distribution
- Class balance
- Temporal coverage
- Feature overlap between positive and negative populations
- Number and size of giant components
- Seed and generator configuration

---

## User Flows

### Flow 1: Analyst reviews a flagged ring

1. Analyst opens Risk Control Center, sees summary stats (transactions analyzed, rings detected, exposure, expected loss).
2. Analyst clicks the highest-risk ring in the ranked list.
3. System shows the relationship graph for that ring, plus a signal breakdown ("7 accounts share Device 91", "83% refund similarity", etc.).
4. System shows the LLM-generated plain-language explanation, grounded in the same signals.
   - Alternative path: analyst hovers a node in the graph to see that account's individual signal contribution.
   - Error state: if the LLM explanation service fails, the UI still shows the signal breakdown and score — explanation is additive, not load-bearing.
5. Analyst chooses Allow, Watch, Manual Review, or Escalate.
6. The selected action is written to the audit trail.
7. No action automatically blocks a transaction or account.

### Flow 2: Judge/demo walkthrough

1. Briefly show normal transaction traffic.
2. Demonstrate a coordinated ring appearing in the synthetic stream.
3. System surfaces the ring with size, exposure, and risk score.
4. Judge/viewer opens the ring to see the relationship graph and evidence.
5. System shows the explanation and contributing signals.
6. System shows threshold/expected-cost tradeoffs.
7. System shows held-out evaluation metrics.
8. Team briefly demonstrates that the same infrastructure pattern can exist in a legitimate hard-negative cluster without being escalated.
9. If asked, team shows ring-level split logic and benchmark reproducibility.

### Flow 3: LLM failure

1. Detection succeeds normally.
2. LLM explanation request fails or times out.
3. UI displays deterministic evidence and risk score.
4. UI labels the explanation service as unavailable.
5. Analyst workflow remains usable.

---

## Non-Functional Requirements

### Performance

- **Load Time:** Dashboard initial load under 3 seconds on the demo dataset size (~10–25k transactions).
- **Concurrent Users:** Single-demo scale; not a production concurrency target.
- **Response Time:** Ring detail view (graph + deterministic evidence) renders within 2 seconds of click.
- **LLM Response:** LLM explanation is non-blocking and may load after deterministic evidence.
- **Benchmark Runtime:** Dataset generation and Tier 1 evaluation should complete locally within a practical hackathon development cycle.

### Security

- **Authentication:** Not required for hackathon demo scope; noted as a gap for production.
- **Authorization:** N/A for demo; production version would need analyst-role gating on Escalate action.
- **Data Protection:** All data synthetic — no real PII, card numbers, or transaction data used at any stage.
- **Defense-only constraint:** No feature, API, prompt, or output should provide instructions for committing fraud, evading detection, or optimizing abuse.

### Compatibility

- **Devices:** Desktop browser (demo/judging context).
- **Browsers:** Latest Chrome/Edge (sufficient for a hackathon demo).
- **Screen Sizes:** Standard laptop/projector resolution (1280×720 and up).

### Accessibility

- **Compliance Level:** Not a formal WCAG target for the hackathon, but core information must remain understandable without relying exclusively on color.
- **Specific Requirements:** Risk status must use text labels and icons in addition to color; graph evidence should be accompanied by textual summaries.

---

## Technical Specifications

### Frontend

- **Technology Stack:** React dashboard + graph visualization.
- **Design System:** Minimal custom styling — clarity over polish; graph visualization is the centerpiece.
- **Responsive Design:** Not prioritized; single target viewport for demo.
- **Primary Screens:**
  - Risk Control Center
  - Ring Details / Investigator View
  - Threshold & Cost Analysis
  - Evaluation / Benchmark View

### Backend

- **Technology Stack:** Python (FastAPI) for the scoring/evaluation service.
- **API Requirements:**
  - `GET /rings`
  - `GET /rings/{id}`
  - `GET /rings/{id}/evidence`
  - `POST /rings/{id}/review`
  - `GET /metrics`
  - `GET /threshold-analysis`
  - `GET /benchmark`
  - `POST /explain`
- **Database:** SQLite or local Parquet/CSV files for hackathon scale; no need for a production database.
- **Evaluation:** Offline batch evaluation must be reproducible separately from the UI.

### Infrastructure

- **Hosting:** Local/demo-only; no deployment requirement for the buildathon.
- **Scaling:** Not a requirement — dataset size fixed at hackathon scale (10k–50k transactions).
- **CI/CD:** Not required; however, a single benchmark command should be reproducible from a clean environment.
- **Reproducibility:** Repository must include dependency lockfile, generator configuration, seed, benchmark configuration, and model/version metadata.

### Model Layers

#### Tier 1 — Deterministic Baseline

- Relationship graph
- Candidate connected components
- Documented rule-based signal extraction
- Deterministic risk score
- Hard-negative handling
- Baseline comparisons

#### Tier 2 — Supervised ML

- Engineered component/behavioral features
- XGBoost or equivalent tabular model
- Threshold calibration
- Expected-cost optimization
- Ablation analysis

#### Tier 3 — Graph ML (optional)

- GraphSAGE or another GNN
- Explicit comparison against Tier 1 and Tier 2
- Only pursued after MVP stability

---

## Evaluation Protocol

### Split Strategy

The evaluation protocol must prevent both label leakage and structural leakage.

- Entire injected rings remain within a single split.
- Legitimate hard-negative clusters remain within a single split where applicable.
- Threshold selection occurs only on the validation set.
- The test set is evaluated only after the threshold is frozen.
- No test-set statistics may be used to tune model weights, feature engineering, threshold, or generator parameters.
- **Chronological ordering is mandatory for the primary benchmark:** all training data must occur before validation data, and all validation data must occur before test data.
- Entire injected rings remain within a single split.
- Legitimate hard-negative clusters remain within a single split where applicable.
- Exact split dates/period boundaries, random seed, and configuration must be recorded.

### Primary Metrics

Report:

- Precision
- Recall
- F1
- False-positive rate
- Ring recovery rate
- Expected financial loss
- Manual-review rate where applicable

### Metric Uncertainty

Where sample size permits and time remains after Tier 1 is stable, report bootstrap
confidence intervals for:

- Precision
- Recall
- F1
- False-positive rate

This is optional polish. Wide or uninformative intervals should be reported honestly;
confidence intervals must never delay Tier 1 data integrity, evaluation, or demo readiness.
Point estimates must not be presented as evidence of robustness on their own.

### Baseline Comparisons

At minimum compare:

1. Random classifier
2. Shared-device-only rule
3. Shared-IP-only rule
4. Simple transaction-level classifier
5. Deterministic ring scorer
6. XGBoost scorer, if Tier 2 is completed
7. GNN scorer, if Tier 3 is completed

### Ablation Tests

Report performance after removing:

- Device relationship signals
- IP relationship signals
- Payment-instrument signals
- Temporal signals
- Behavioral/refund signals

The purpose is to demonstrate that performance comes from meaningful combination of signals rather than a single shortcut.

---

## False-Positive Cost Model

The operating threshold must be chosen using **expected financial loss as the primary
decision metric**, rather than F1 alone. Precision, recall, F1, false-positive rate, and
ring recovery remain supporting evidence.

### Cost Inputs

False-positive, false-negative, and manual-review costs must be traceable to the synthetic dataset's own financial exposure figures.

Examples of derivation:

- False-negative cost based on median/weighted exposure of a missed ring or missed high-risk transaction.
- False-positive cost based on the expected business impact of incorrectly escalating a legitimate account or cluster.
- Manual-review cost based on a documented synthetic analyst effort assumption.

Arbitrary round-number costs should not be presented without a derivation.

### Threshold Analysis

The system must show multiple operating thresholds, including at least:

- Precision
- Recall
- False-positive count/rate
- False-negative count/rate
- Manual reviews
- Expected loss

The selected operating threshold is chosen on validation data only.

The final test-set result is reported after the threshold is frozen.

### Abstention

The risk engine should support an uncertainty-aware review state:

- **Low risk** → Allow
- **Medium risk** → Watch
- **Uncertain / ambiguous** → Manual Review
- **High risk** → Escalate

The objective is not to force every case into a binary classification.

---

## LLM Explanation Contract

The LLM is an explanation layer, not the authoritative detector.

### Inputs

The LLM receives structured, system-generated evidence such as:

- Component/ring ID
- Number of accounts
- Shared devices
- Shared IPs
- Shared payment instruments
- Temporal concentration
- Refund/behavioral signals
- Risk score
- Contributing feature weights or ranked signals

### Constraints

The LLM must:

- Reference only supplied evidence.
- Never invent transaction values, counts, or entities.
- Never change the underlying risk score.
- Never create a new detection decision.
- Never override deterministic/ML evidence.
- Return structured explanation fields before natural-language rendering where practical.
- Fall back to a deterministic evidence summary if the LLM fails.

### Example Explanation

> "This cluster was escalated because 7 accounts share Device 91, 4 of those accounts also share a payment instrument, and the accounts produced a concentrated transaction burst within 11 minutes. These combined signals are substantially stronger than the merchant's normal shared-device patterns."

---

## Analytics & Monitoring

- **Key Metrics:** Precision, recall, F1, false-positive rate, ring recovery rate, expected financial loss, manual-review rate, benchmark reproducibility.
- **Events:** Analyst review actions (Allow, Watch, Manual Review, Escalate) captured locally for demo auditability.
- **Dashboards:** The Risk Control Center is the primary dashboard; a separate Evaluation View presents benchmark methodology and threshold analysis.
- **Alerting:** Out of scope for demo.
- **Audit Trail:** Every ring review should record timestamp, ring ID, risk score, threshold, evidence snapshot, and analyst action.

---

## Release Planning

### MVP (v1.0) — Tier 1, must-have for submission

**Features:**

- Synthetic generator
- Synthetic data validation
- One abuse-ring type initially
- One hard-negative type initially
- Relationship graph
- Connected-component hygiene
- Deterministic risk score
- Baseline sanity checks
- Ring-level split
- Leakage-safe evaluation
- Precision/recall/FP evaluation
- False-positive cost model
- Threshold analysis
- Investigator console
- Manual-review state
- Basic audit trail
- Reproducible benchmark runner

**Build Rule:**

Do not start Tier 2 until all Tier 1 conditions are satisfied.

**Tier 1 completion gate:**

- Dataset generation is reproducible.
- At least one abuse ring and one hard negative pass end-to-end.
- Graph construction is validated.
- Held-out evaluation runs automatically.
- Baseline metrics are reproducible.
- No structural leakage is detected.
- Cost model has documented derivation.
- Core UI can display the evidence and action state.

**Success Criteria:** End-to-end pipeline runs on synthetic data and produces honest held-out metrics without leakage.

### v1.1 — Tier 2

- Additional abuse-ring types
- Additional hard-negative types
- XGBoost scorer
- Feature engineering refinement
- False-positive cost/threshold refinement
- Metric confidence intervals
- Ablation analysis
- Interactive graph explorer
- LLM explanation layer

**Entry condition:** Tier 1 is stable and reproducible.

### v1.2 — Demo polish

- Better graph interactions
- Faster ring investigation
- Improved audit trail presentation
- Threshold/cost visualization
- Lightweight evaluation methodology view
- Reproducibility command/demo

**UI constraint:** Risk Control Center and Ring Details are the only fully polished
screens. Threshold/Cost and Evaluation/Benchmark should be functional reference views,
not separate UI projects.

### v2.0 — Tier 3, stretch only

- GraphSAGE/GNN second-stage scorer
- Compare against Tier 1 and Tier 2
- Additional research-oriented graph features

**Entry condition:** Tier 1, Tier 2, and the complete demo flow are already stable.

---

## Time Budget & Execution Guardrails

Time budgets are planning constraints, not promises. They exist to prevent Tier 1 work
from expanding indefinitely under hackathon pressure.

### Tier 0 — Dataset + evaluation foundation
**Target: 20–25% of available build time**

- Generator skeleton
- One shared-device ring
- One family hard negative
- Fixed seed/configuration
- Relationship graph
- Chronological + ring-level split
- Baseline evaluation runner

**Time trigger:** If the first end-to-end benchmark cannot run within the first ~25% of
available build time, freeze scope and simplify the generator before proceeding.

### Tier 1 — Defensible MVP
**Target: 35–40% of available build time**

- Full deterministic scorer
- Hard-negative validation
- Baseline comparisons
- Leakage checks
- Expected-cost threshold selection
- Investigator console
- Audit trail
- Core demo flow

**Time trigger:** At ~65% of total build time, Tier 1 must either be submission-ready
or be frozen. No additional ring types, GNN work, or UI polish should delay the floor demo.

### Tier 2 — Differentiation
**Target: 20–25% of available build time**

- XGBoost scorer
- Feature/ablation analysis
- Additional ring/hard-negative types
- LLM explanation
- Threshold/cost visualization polish

**Time trigger:** Tier 2 stops immediately if it threatens the Tier 1 demo or benchmark.

### Tier 3 — Stretch
**Target: maximum 10–15% of available build time**

- GraphSAGE / GNN
- Advanced graph experiments
- Additional research-oriented features

**Time trigger:** Tier 3 is abandoned at the first sign of instability, reproducibility
regression, or demo risk.

### Final Freeze Window

Reserve the final ~15% of available build time for:

- benchmark rerun
- bug fixing
- demo rehearsal
- fallback verification
- packaging/submission

No new major features should enter during the final freeze window.

---

## Fallback Demo Path

The project has a predefined fallback story requiring **no Tier 2 or Tier 3 features**.

### Fallback Demo: "The Defensible Risk Baseline"

1. Generate a reproducible synthetic benchmark.
2. Detect a shared-device abuse ring with the deterministic graph scorer.
3. Show a legitimate family cluster sharing the same device pattern but remaining below the escalation threshold.
4. Open the ring graph and show the evidence breakdown.
5. Show the validation-derived threshold and expected-loss table.
6. Show the frozen-threshold held-out precision, recall, false-positive rate, and ring recovery.
7. Show the ring-level + chronological split methodology.
8. Close with the audit trail and defense-only review action.

**Submission rule:** A fully working Tier 1 fallback is considered the minimum viable
demo. Tier 2 and Tier 3 are enhancements, not dependencies for submission.

---

## Scope Kill-Switch

The project must prioritize a complete, defensible system over model sophistication.

### Hard rules

- Do not begin Tier 2 until Tier 1 passes its completion gate.
- Do not begin Tier 3 until Tier 2 and the demo are stable.
- Do not add a new ring type if the current evaluation pipeline is not reproducible.
- Do not add LLM functionality if it risks delaying the benchmark or UI.
- Do not replace a working deterministic baseline with a more complex model unless the comparison is measurable.
- A working simple detector with honest evaluation is preferred over a half-working GNN.

---

## Demo Plan (5 Minutes)

### 0:00–0:35 — Problem + thesis

> "Traditional fraud detection sees transactions. RiskMesh sees the relationships connecting them."

Immediately show the key product outcome and the fact that legitimate shared infrastructure is also modeled.

### 0:35–1:35 — Live ring discovery

- Show normal synthetic activity briefly.
- Introduce a coordinated ring.
- Show the relationship graph forming.
- Surface ring size, exposure, and score.

### 1:35–2:25 — Investigation

- Open the ring.
- Highlight shared attributes and temporal signals.
- Show deterministic evidence.
- Optionally show the LLM explanation.

### 2:25–3:45 — Threshold economics

Show the threshold table and explain:

> "We do not choose the threshold that maximizes F1. We choose the operating point that minimizes expected financial loss under explicit cost assumptions."

Show:

- Precision
- Recall
- FP/FN tradeoff
- Expected loss

### 3:45–4:30 — Held-out evaluation

Show:

- Ring-level split
- Chronological train/validation/test ordering
- Test isolation
- Precision / recall / FP rate
- Expected loss as the primary decision metric
- Confidence intervals only if already available

### 4:30–5:00 — Hard negative + fallback-proof ending

Show a legitimate shared-infrastructure cluster, such as a hostel/office/family group.

Then briefly show the audit trail and review state.

End with:

> "Shared infrastructure does not equal fraud. RiskMesh is looking for coordinated behavior across the relationship graph — and it prices the cost of being wrong."

**Fallback rule:** If Tier 2/3 features are unavailable, the same demo is delivered using
the Tier 1 deterministic scorer, expected-loss thresholding, hard-negative comparison,
and held-out evaluation.

---

## Open Questions & Assumptions

- **Question 1:** What exact false-positive/false-negative/review cost derivations produce the most defensible financial-risk framing on the synthetic dataset?
- **Question 2:** None for the core MVP. Temporal ordering is mandatory: train, validation, and test periods must be chronologically ordered in the primary benchmark.
- **Question 3:** What graph-size and interaction limits are practical for the chosen frontend visualization library?
- **Question 4:** Should optional Razorpay test-mode integration strengthen the final demo without becoming a dependency for the Track 02 MVP?

- **Assumption 1:** Track 02 can be evaluated primarily through a synthetic, defense-only detector because the public brief emphasizes working detection quality and held-out metrics rather than mandatory payment API execution.
- **Assumption 2:** Judges will value leakage-safe, ring-level evaluation and honest cost tradeoffs as evidence of technical maturity.
- **Assumption 3:** Expected financial loss is the primary decision criterion; precision, recall, F1, false-positive rate, and ring recovery are supporting evidence.
- **Assumption 4:** A working Tier 1 system with strong evaluation beats a half-working Tier 3 GNN in the pitch.
- **Assumption 5:** Train, validation, and test periods are chronologically ordered in the primary benchmark.
- **Assumption 6:** The detector's authoritative decision logic must remain separate from the LLM explanation layer.

---

## Appendix

### Competitive Analysis

- **Generic transaction classifiers:** Treat accounts independently; miss coordinated structure; easy to build and easy to forget.
- **Commercial fraud/risk platforms:** Mature, production-grade systems that provide a reference point for rigor, explainability, graph relationships, and operational workflows. The project should borrow those principles without claiming production scale.
- **Generic LLM fraud assistants:** Can generate explanations but may lack defensible detection metrics and auditable decision logic. RiskMesh intentionally avoids using an LLM as the primary detector.

### User Research Findings

- Formal user research has not been conducted; this PRD is written from the buildathon requirements, technical planning, and domain reasoning.
- The primary user problem is treated as coordinated-abuse visibility plus alert-fatigue reduction.

### AI Conversation Insights

- **Conversation 1:** Track selection research — compared all 5 buildathon tracks against the project's software/AI/backend strengths; initially recommended Track 03, revised to Track 02 after deeper research into technical differentiation and the brief's own "abuse-ring sentinel" example direction.
- **Conversation 2:** Scoped the Track 02 project into a tiered build plan (deterministic baseline → XGBoost → GNN stretch) with ring-based evaluation splitting and false-positive cost economics as the core differentiator.
- **Conversation 3:** Identified synthetic-data quality as a primary project risk and narrowed the first implementation slice to one abuse-ring type plus one legitimate hard negative.
- **AI-Generated Edge Cases:** Legitimate shared-IP clusters (hostel Wi-Fi, office networks, family accounts); common infrastructure creating giant graph components; trivially separable synthetic data; temporal leakage; ring leakage across splits; threshold tuning on the test set; LLM hallucination of unsupported evidence.
- **AI-Suggested Improvements:** Derive costs from dataset exposure rather than arbitrary constants; add baseline and ablation comparisons; use confidence intervals where possible; make false-positive economics a Must-have; separate the LLM explanation layer from authoritative detection; use a demo that gives more time to threshold/cost tradeoffs and hard-negative behavior.

### Glossary

- **Ring:** A connected group of accounts, devices, IPs, or payment instruments exhibiting coordinated abuse behavior (as opposed to independent, unrelated fraud).
- **Hard negative:** A legitimate cluster that shares attributes with fraud patterns (e.g., shared IP) but is not abuse — used to test false-positive resistance.
- **Ring-level split:** A train/test split performed on whole rings rather than individual transactions, preventing structural information leakage between splits.
- **Expected cost:** The weighted sum of false-positive cost, false-negative cost, and manual-review cost at a given detection threshold — used to choose an operating point instead of optimizing a single metric like F1.
- **Ablation:** An experiment that removes one group of signals/features to measure its contribution to system performance.
- **Abstention:** A deliberate decision to defer an uncertain case to manual review rather than forcing an automated classification.
- **Connected-component hygiene:** Controls that prevent common attributes such as highly shared IPs from merging unrelated populations into meaningless giant graph components.
