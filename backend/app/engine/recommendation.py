"""Prioritization scorer + candidate -> recommendation row builder (spec Parts 8-9).

Turns root_cause.py's raw candidate dicts into rows shaped like the
`recommendations` table. No LLM involvement — rationale text is filled in
later by llm_rationale.py from these already-decided numbers.
"""
from __future__ import annotations

# urgency_weight by anomaly severity. Not pinned by the spec; chosen so a
# high-severity anomaly's recommendation is weighted a full point, medium is
# meaningfully discounted, and low barely nudges priority.
URGENCY_WEIGHT_BY_SEVERITY = {"high": 1.0, "medium": 0.6, "low": 0.3}
# Candidates with no linked anomaly (e.g. the cross-campaign budget
# reallocation candidate, which compares two campaigns rather than reacting
# to one flagged anomaly) default to medium urgency.
DEFAULT_URGENCY_WEIGHT = 0.6

# Non-budget impact-math assumptions (spec doesn't specify these — documented
# here). Both proxies value a "% improvement" against the campaign's recent
# average daily spend, since spend is the one baseline every candidate has.
ASSUMED_CPA_IMPROVEMENT_PCT = 0.10     # bidding fix: assumed achievable CPA improvement
ASSUMED_CREATIVE_RECOVERY_PCT = 0.15   # creative refresh: assumed CTR/revenue recovery


def _lookup_anomaly(anomalies: list[dict], anomaly_id) -> dict | None:
    if anomaly_id is None:
        return None
    for a in anomalies:
        if a.get("anomaly_id") == anomaly_id:
            return a
    return None


def _expected_impact(candidate: dict) -> tuple[float, float]:
    """Returns (expected_impact_value, expected_impact_pct). expected_impact_pct
    is in PERCENTAGE POINTS (e.g. 10.0 means 10%), not a 0-1 fraction - the
    frontend's formatPercent() appends '%' to this number directly."""
    ctype = candidate["type"]

    if ctype == "budget":
        # Spec-specified formula: revenue delta = amount shifted * receiving
        # campaign's historical ROAS.
        amount_shifted = candidate.get("amount_shifted", 0.0) or 0.0
        receiving_roas = candidate.get("receiving_campaign_roas", 0.0) or 0.0
        impact_value = amount_shifted * receiving_roas
        # % return relative to the amount of spend actually being moved
        impact_pct = ((impact_value / amount_shifted) * 100) if amount_shifted else 0.0
        return impact_value, impact_pct

    if ctype == "bidding":
        # Proxy (spec doesn't fully specify non-budget math): value the
        # assumed CPA improvement against the campaign's recent average spend.
        recent_spend = candidate.get("recent_spend", 0.0) or 0.0
        impact_value = recent_spend * ASSUMED_CPA_IMPROVEMENT_PCT
        return impact_value, ASSUMED_CPA_IMPROVEMENT_PCT * 100

    if ctype == "creative":
        # Proxy: value the assumed CTR/revenue recovery from a creative
        # refresh against the campaign's recent average spend.
        recent_spend = candidate.get("recent_spend", 0.0) or 0.0
        impact_value = recent_spend * ASSUMED_CREATIVE_RECOVERY_PCT
        return impact_value, ASSUMED_CREATIVE_RECOVERY_PCT * 100

    return 0.0, 0.0


def build_recommendations(
    candidates: list[dict],
    anomalies: list[dict],
    base_confidence_by_type: dict[str, float],
) -> list[dict]:
    recommendations: list[dict] = []

    for candidate in candidates:
        ctype = candidate["type"]
        anomaly = _lookup_anomaly(anomalies, candidate.get("anomaly_id"))
        severity = anomaly["severity"] if anomaly else None
        urgency_weight = URGENCY_WEIGHT_BY_SEVERITY.get(severity, DEFAULT_URGENCY_WEIGHT)

        base_confidence = base_confidence_by_type.get(ctype, 0.5)
        rule_confidence = candidate.get("confidence", base_confidence)
        # Simple average: base_confidence (per-type prior, possibly nudged by
        # adjust_confidence) and rule_confidence (how cleanly THIS rule fired)
        # are independent signals, so we blend them evenly rather than
        # privileging one.
        confidence_score = (base_confidence + rule_confidence) / 2

        impact_value, impact_pct = _expected_impact(candidate)
        priority_score = impact_value * confidence_score * urgency_weight

        recommendations.append(
            {
                "campaign_id": candidate["campaign_id"],
                "anomaly_id": candidate.get("anomaly_id"),
                "type": ctype,
                "expected_impact_value": impact_value,
                "expected_impact_pct": impact_pct,
                "confidence_score": confidence_score,
                "priority_score": priority_score,
                "status": "pending",
                # Not a `recommendations` table column — carried through so the
                # caller can feed llm_rationale.py without re-deriving context.
                "_rationale_input": candidate.get("rationale_input", {}),
            }
        )

    return recommendations


def adjust_confidence(base_confidence_by_type: dict, type_stats: dict) -> dict:
    """Nudge each type's base confidence toward its observed approval rate
    (spec Part 9). type_stats: {type: {"approved_count": int, "rejected_count": int}}.

    Blend weight: up to 30% observed / 70% base once there are >= 10 decisions
    for that type; below 10 decisions the observed weight is scaled down
    proportionally, so a couple of early approvals/rejections can't swing
    confidence wildly. These weights aren't pinned by the spec — chosen so the
    fixed base still dominates early on.
    """
    MAX_OBSERVED_WEIGHT = 0.3
    MIN_DECISIONS_FOR_FULL_WEIGHT = 10

    adjusted: dict[str, float] = {}
    for rtype, base_confidence in base_confidence_by_type.items():
        stats = type_stats.get(rtype, {})
        approved = stats.get("approved_count", 0)
        rejected = stats.get("rejected_count", 0)
        total = approved + rejected

        if total == 0:
            adjusted[rtype] = base_confidence
            continue

        observed_rate = approved / total
        sample_weight = min(total / MIN_DECISIONS_FOR_FULL_WEIGHT, 1.0)
        observed_weight = MAX_OBSERVED_WEIGHT * sample_weight
        base_weight = 1 - observed_weight

        adjusted[rtype] = base_confidence * base_weight + observed_rate * observed_weight

    return adjusted
