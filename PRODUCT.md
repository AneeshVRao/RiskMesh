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

- **Benchmark:** 5,962 transactions, 789 accounts, 24 injected rings, 24
  legitimate family hard-negative clusters, 100 candidate components. Seed
  20260824, config fingerprint `7c1e4fb2b329796c`.
- **Split:** chronological + ring-level. Test = 31 components (8 positive,
  23 negative, 8 of the negatives carrying a family cluster).
- **Scorer:** `A_baseline`, seven signals, weights frozen. Each signal emits
  `raw`, `normalized`, `weight`, `contribution` and a human-readable `detail`
  string (e.g. "9 accounts share device d_ring02", "median account age 10
  days"). The evidence view is a render of this structure, not a reconstruction.
- **Binary held-out result:** precision 0.6667, recall 1.0000, F1 0.8000,
  FPR 0.1739, ring recovery 8/8, expected loss 9,392.92 at threshold 0.23.
- **Three-way abstention policy (current):** Allow < 0.23, Review
  [0.23, 0.33), Escalate >= 0.33. Held out: expected loss **6,000.00**, review
  rate 19.35% (6 of 31), and **zero escalated false positives** — all four of
  the binary policy's false positives are family clusters, and all four land in
  the review band.
- **Costs, dataset-derived:** review 500.00, false negative 74,645.29, false
  positive 848.23 (INR).

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
