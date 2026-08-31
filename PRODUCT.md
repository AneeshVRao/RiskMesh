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

- **Benchmark:** 6,059 transactions, 801 accounts, 24 injected rings (70%
  hybrid pool-funded, Phase 10), 24 legitimate family hard-negative clusters,
  105 candidate components. Seed 20260824, config fingerprint
  `c3ee14627c2c2ce2`.
- **Split:** chronological + ring-level. Test = 32 components (8 positive,
  24 negative, 8 of the negatives carrying a family cluster).
- **Scorer:** `A_baseline`, eight signals, weights frozen (re-frozen Phase 11 —
  `D_drop_flagged` won the search and was folded in as the new incumbent). Each
  signal emits `raw`, `normalized`, `weight`, `contribution` and a
  human-readable `detail` string (e.g. "9 accounts share device d_ring02",
  "median account age 10 days"). The evidence view is a render of this
  structure, not a reconstruction.
- **Binary held-out result:** precision 0.6154, recall 1.0000, F1 0.7619,
  FPR 0.2083, ring recovery 8/8, expected loss 8,041.65 at threshold 0.14.
- **Three-way abstention policy (current):** Allow < 0.14, Review
  [0.14, 0.23), Escalate >= 0.23. Held out: expected loss **6,808.33**, review
  rate 15.6% (5 of 32), a 15.3% reduction against the binary policy — 4 of the
  binary policy's 5 false positives (all family clusters) land in the review
  band; the 5th escalates in the three-way policy too.
- **Costs, dataset-derived:** review 500.00, false negative 76,985.91, false
  positive 308.33 (INR, friction only — `deferred_decisions.md` D3 resolved).

## What this product must prove on screen

1. A ring and a family look structurally *identical* (both share a device, an
   IP, often a card) and are separated by behavior: account tenure, burst
   convergence on one merchant, refund rate.
2. Escalations are clean — nothing legitimate gets auto-escalated.
3. Every score decomposes into named evidence with real values. Nothing is a
   black box.
4. False positives cost money, and the operating point was chosen against that
   cost.

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
