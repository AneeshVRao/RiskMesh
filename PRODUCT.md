# PRODUCT.md — RiskMesh

Derived from `PRD.md`, `implementation_plan.md`, and the frozen records in
`experiments/`. No facts invented: every number here traces to a committed
artifact. Written to unblock design tooling that requires product truth; the
authoritative product spec remains `PRD.md`.

## What it is

A defense-only AI risk system that detects **coordinated abuse rings** — not
isolated suspicious transactions — by modeling relationships between accounts,
devices, IPs and payment instruments, and by explicitly pricing the financial
cost of getting a call wrong.

Built for Razorpay Buildathon Track 02 (AI Risk Manager).

## The unique mechanism, in one sentence

Coordinated abuse is visible in the *relationships between* otherwise
normal-looking entities, so RiskMesh scores connected components of a
heterogeneous graph rather than transactions, and routes the genuinely
ambiguous ones to a human instead of forcing a binary call.

## Who uses it, and the real scene

**Primary: a fraud analyst on a risk-ops team.** Moderate technical
proficiency. Lives in a queue-driven review tool for most of a shift, indoors,
under office light, on a desktop browser. Their working problem is not "find
fraud" — it is *alert fatigue*: transaction-level tools miss coordinated abuse
spread across many individually-normal accounts, and drown them in false
alarms. They must be able to justify an escalation to a manager or auditor.

**Secondary but decisive: a buildathon judge**, evaluating in a 5-minute pitch
window, looking for whether metrics are held out, whether false positives are
priced rather than merely minimized, and whether the synthetic benchmark avoids
leakage.

## What is actually built (frozen, real numbers)

**Two thresholds exist on this benchmark, selected by two different
objectives, and neither substitutes for the other — see README "Two Tier 1
operating points" before quoting either number in isolation.**

- **Benchmark:** 19,310 transactions, 2,338 accounts, 3,088 devices, 2,429
  IPs, 2,192 instruments, 40 merchants. 60 injected rings (12 each of 5
  mechanisms — device, ip, instrument, refund, hybrid), 105 legitimate
  hard-negative clusters (60 family, 15 office, 15 hostel, 15 retail), 336
  candidate components. Seed 20260824, config fingerprint
  `fdf4fc217347d36b`.
- **Split:** chronological + ring-level. Test = 112 components (23 positive,
  89 negative, 43 of the negatives carrying a hard-negative cluster).
- **Scorer:** `A_baseline`, eight signals, weights re-frozen by Task 6's
  weight-search re-run (`E_drop_temporal` beat the prior incumbent outright
  on validation expected loss and was folded back in). Current weights:
  `device_sharing` 0.3929, `instrument_pool_concentration` 0.2143,
  `failure_refund_rate` 0.2143, `account_newness` 0.1786, and four signals
  (`temporal_burst`, `ip_sharing`, `instrument_sharing`,
  `merchant_concentration`) at 0.0000. Each signal emits `raw`, `normalized`,
  `weight`, `contribution` and a human-readable `detail` string. The
  evidence view is a render of this structure, not a reconstruction.
- **Read A — `out/threshold.json`, F1-selected on validation. What the API
  serves.** Threshold 0.22. Held out: precision 0.7200, recall 0.7826, F1
  0.7500, FPR 0.0787, ring recovery 13/20, on 112 test components.
- **Read B — `weight_policy.json` `held_out`, cost-selected on validation via
  the weight search's own expected-loss objective.** Threshold 0.10. Held
  out (same 112 components): precision 0.3793, recall 0.9565, F1 0.5432, FPR
  0.4045, ring recovery 16/20, **expected loss 92,263.55**. **A Must-have PRD
  compliance gap:** the PRD requires the *shipped* threshold to be
  loss-selected; Read A, not Read B, is what ships. Disclosed in
  `deferred_decisions.md` D4, not fixed.
- **Three-way abstention policy (current, layered on Read B's threshold):**
  the free search selects a **non-degenerate band** for the first time —
  Allow < 0.10, Review [0.10, 0.20), Escalate >= 0.20. Held out: three-way
  expected loss **75,529.35** against the binary policy's 92,263.55 on the
  same rows — an **18.1% improvement**, the first held-out run where Review
  beats rather than ties the binary policy.
- **Costs, dataset-derived:** review 500.00, false negative 41,748.15, false
  positive 597.65 (INR, friction only — `deferred_decisions.md` D3 resolved),
  `C_fn`/`C_fp` ratio 69.9:1 — the least lopsided this project has derived.
- **Tier 2 (XGBoost):** no feasible candidate. All four configurations
  over-separate the current, larger training split (124 components);
  `positives_below_max_negative` 0.0435-0.2174, all below the 0.45 floor.
  No held-out read taken.
- **Tier 3 (GraphSAGE, stretch):** `G2_two_layer` feasible, threshold 0.03.
  Held out: F1 0.5412, expected loss **54,308.35** — at each model's own
  cost-selected operating point (Read B for Tier 1), F1s are effectively
  tied (0.002 apart) and GraphSAGE's expected loss is ~41% lower, which
  matters because expected loss is the PRD's stated primary decision metric.

## What this product must prove on screen

1. A ring and a family look structurally *identical* (both share a device, an
   IP, often a card) and are separated by behavior: account tenure, burst
   convergence on one merchant, refund rate.
2. Escalations are clean — nothing legitimate gets auto-escalated.
3. Every score decomposes into named evidence with real values. Nothing is a
   black box.
4. False positives cost money, and a cost-selected operating point exists and
   is frozen — though the threshold the console currently serves is
   F1-selected, not the cost-selected one; see "What is actually built"
   above and `deferred_decisions.md` D4.

## Hard constraints

- **Defense-only.** No feature, output or prompt may aid committing fraud or
  evading detection.
- **No automatic blocking.** The analyst acts; the system recommends. Actions
  are Allow / Watch / Manual Review / Escalate, all written to an audit trail.
- **All data synthetic.** No real PII, cards, or transactions, at any stage.
- **The LLM never detects.** It explains, grounded strictly in supplied
  evidence, and the interface stays fully usable when it is unavailable.
- **Status may never be conveyed by color alone** — text labels and icons too.
- Desktop browser, 1280x720 and up. Dashboard load under 3s; ring detail under
  2s.

## Surfaces

Risk Control Center (primary), Ring Details / Investigator View, Threshold &
Cost Analysis, Evaluation / Benchmark View.
