"""The only two formulas the API owns, and the frozen peer rule.

Kept in one small module so they can be tested directly against the pipeline's
own values. The API's band logic must agree with `abstention.py`'s, and the
contribution formula must agree with `score.py`'s -- a test can prove both, but
only if they live somewhere a test can reach without starting a web server.
"""

from __future__ import annotations

ALLOW, REVIEW, ESCALATE = "allow", "review", "escalate"


def action_for(score: float, t_lo: float, t_hi: float) -> str:
    """Three-way disposition. Same boundaries as abstention.three_way_stats()."""
    if score < t_lo:
        return ALLOW
    if score < t_hi:
        return REVIEW
    return ESCALATE


def contribution(weight: float, normalized: float) -> float:
    """What this signal added to the score.

    Mirrors score.py's `round(w[name] * clipped, 6)` exactly, including the
    rounding. components.csv stores raw and norm but not contribution, so this
    recomputes it -- and it must reproduce the frozen number, not merely
    approximate it.
    """
    return round(weight * normalized, 6)


# --- peer selection -------------------------------------------------------
# Frozen rule: `nearest_opposite_label_prefer_family`.
#
# A documented heuristic, not a derived optimum. Recorded so a reader can
# disagree with it explicitly rather than discover it by reading code.
#
#   1. same split as the subject
#   2. opposite is_positive, excluding the subject itself
#   3. prefer has_family -- the panel is "ring vs HARD-NEGATIVE CLUSTER"
#      (family/office/hostel/retail), and a generic background negative
#      would not tell that story
#   4. minimise |score difference|, rounded to 9dp to avoid float-repr ties
#   5. tiebreak A: higher score wins (prefer the harder case)
#   6. tiebreak B: lexicographically smallest component_id -- a total order, so
#      the result cannot depend on CSV row order
#
# Verified over the frozen test split: yields c_a00533 -> c_a00727, zero
# distance ties occur, and selection is identical across shuffled input. Steps 5
# and 6 never fire on today's data; they are specified because another seed
# could produce a tie and that is not a thing to discover at request time.
PEER_RULE = "nearest_opposite_label_prefer_family"


def select_peer(subject: dict, pool: list[dict]) -> dict | None:
    candidates = [c for c in pool
                  if c["split"] == subject["split"]
                  and c["is_positive"] != subject["is_positive"]
                  and c["component_id"] != subject["component_id"]]
    if not candidates:
        return None
    family = [c for c in candidates if c["has_family"]]
    tier = family or candidates
    return min(tier, key=lambda c: (
        round(abs(c["score"] - subject["score"]), 9),
        -c["score"],
        c["component_id"],
    ))


def separating_fields(subject: dict, peer: dict) -> list[str]:
    """Which comparison rows actually differ enough to be the reason.

    The UI highlights these. Computing it here rather than client-side keeps the
    analysis out of the stylesheet.
    """
    out = []
    for field, rel in (("median_account_age_days", 2.0),
                       ("burst_fraction", 1.5),
                       ("max_accounts_per_ip", 2.0)):
        a, b = subject.get(field), peer.get(field)
        if a is None or b is None:
            continue
        lo, hi = sorted((float(a), float(b)))
        if lo <= 0 or hi / lo >= rel:
            out.append(field)
    return out
