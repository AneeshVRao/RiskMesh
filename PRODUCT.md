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

- **Benchmark:** 6,052 transactions, 799 accounts, 24 injected rings (70%
  hybrid pool-funded, Phase 10), 24 legitimate family hard-negative clusters,
  100 candidate components. Seed 20260824, config fingerprint
  `c3ee14627c2c2ce2` (unchanged by Phase 12's generator fix, which touches
  code, not config fields).
- **Split:** chronological + ring-level. Test = 31 components (8 positive,
  23 negative, 8 of the negatives carrying a family cluster).
- **Scorer:** `A_baseline`, eight signals, weights frozen (re-frozen Phase 11,
  reconfirmed outright by Phase 12's re-run after the generator fix —
  `D_drop_flagged` ties it exactly but is a no-op against the current
  weights, so the incumbent wins the tie-break without any fold-back). Each
  signal emits `raw`, `normalized`, `weight`, `contribution` and a
  human-readable `detail` string (e.g. "9 accounts share device d_ring02",
  "median account age 10 days"). The evidence view is a render of this
  structure, not a reconstruction.
- **Binary held-out result:** precision 0.7000, recall 0.8750, F1 0.7778,
  FPR 0.1304, ring recovery 7/8, expected loss 74,595.13 at threshold 0.18
  (one missed ring dominates this figure at a 171.7:1 `C_fn`/`C_fp` ratio).
- **Three-way abstention policy (current):** the free search selects a
  **degenerate band**, Allow < 0.18, Escalate >= 0.18 (Review is empty:
  `t_lo = t_hi = 0.18`) — `A_baseline` reaches a perfect validation confusion
  matrix at that threshold, leaving nothing for Review to rescue or waive.
  Held out: expected loss **74,595.13**, bit-for-bit identical to the binary
  policy on the same rows, a 0% change rather than a reduction.
- **Costs, dataset-derived:** review 500.00, false negative 68,399.84, false
  positive 398.43 (INR, friction only — `deferred_decisions.md` D3 resolved).

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
