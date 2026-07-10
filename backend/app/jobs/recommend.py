"""Root cause + recommendation job (spec Part 12, step 3). Reads unresolved
anomalies plus related tables, writes root causes back onto anomalies and
full recommendation rows (with Claude-generated rationale) into
recommendations. Runs after the detection job."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app import db
from app.config import settings
from app.engine.llm_rationale import FALLBACK_RATIONALE, build_client, generate_rationale
from app.engine.recommendation import adjust_confidence, build_recommendations
from app.engine.root_cause import apply_root_causes

LOOKBACK_DAYS = 120
# Cross-campaign budget-reallocation candidates aren't tied to one anomaly, so
# they'd otherwise regenerate every 15-min cycle for as long as the ROAS gap
# persists - suppress if a pending one already exists for the same campaign.
DEDUP_WINDOW_DAYS = 7


def _load_type_stats() -> dict:
    rows = db.query("SELECT * FROM recommendation_type_stats")
    return {r["type"]: r for r in rows}


def _has_pending_reallocation(campaign_id: str) -> bool:
    since = date.today() - timedelta(days=DEDUP_WINDOW_DAYS)
    rows = db.query(
        """
        SELECT rec_id FROM recommendations
        WHERE campaign_id = :campaign_id
          AND type = 'budget'
          AND anomaly_id IS NULL
          AND status = 'pending'
          AND created_at >= :since
        """,
        {"campaign_id": campaign_id, "since": since},
    )
    return len(rows) > 0


def run_recommendation() -> dict:
    since = date.today() - timedelta(days=LOOKBACK_DAYS)

    unresolved = db.query("SELECT * FROM anomalies WHERE root_cause_label IS NULL")

    # The cross-campaign ROAS-reallocation check runs over ALL campaigns (it
    # doesn't require an anomaly to fire), so pull broadly rather than scoping
    # to just the unresolved anomalies' campaigns.
    daily_metrics = pd.DataFrame(
        db.query("SELECT * FROM campaign_daily_metrics WHERE date >= :since", {"since": since})
    )
    campaigns = pd.DataFrame(db.query("SELECT * FROM campaigns"))
    budget_changes = pd.DataFrame(db.query("SELECT * FROM budget_change_log"))
    audience = pd.DataFrame(
        db.query("SELECT * FROM audience_segments WHERE date >= :since", {"since": since})
    )
    creatives = pd.DataFrame(
        db.query("SELECT * FROM creatives WHERE date >= :since", {"since": since})
    )

    if not unresolved and daily_metrics.empty:
        return {"anomalies_processed": 0, "recommendations_created": 0}

    resolved_anomalies, candidates = apply_root_causes(
        unresolved, daily_metrics, budget_changes, audience, creatives, campaigns
    )

    for a in resolved_anomalies:
        if a.get("root_cause_label") is not None:
            db.execute(
                "UPDATE anomalies SET root_cause_label = :label, root_cause_confidence = :conf WHERE anomaly_id = :id",
                {
                    "label": a["root_cause_label"],
                    "conf": a["root_cause_confidence"],
                    "id": a["anomaly_id"],
                },
            )

    candidates = [
        c
        for c in candidates
        if not (c["type"] == "budget" and c.get("anomaly_id") is None and _has_pending_reallocation(c["campaign_id"]))
    ]

    type_stats_rows = _load_type_stats()
    base_confidence = {t: r["base_confidence"] for t, r in type_stats_rows.items()}
    type_stats = {
        t: {"approved_count": r["approved_count"], "rejected_count": r["rejected_count"]}
        for t, r in type_stats_rows.items()
    }
    adjusted_confidence = adjust_confidence(base_confidence, type_stats)

    recs = build_recommendations(candidates, resolved_anomalies, adjusted_confidence)

    anomaly_by_id = {a["anomaly_id"]: a for a in resolved_anomalies if a.get("anomaly_id") is not None}
    campaign_names = (
        {c["campaign_id"]: c["campaign_name"] for c in campaigns.to_dict("records")} if not campaigns.empty else {}
    )
    llm_client = build_client(settings.openrouter_api_key) if settings.openrouter_api_key else None

    inserted = []
    for rec in recs:
        rationale_input = rec.pop("_rationale_input", {})
        linked = anomaly_by_id.get(rec.get("anomaly_id"))
        metric = linked["metric"] if linked else "cross_campaign_budget_efficiency"
        root_cause_label = (linked["root_cause_label"] if linked else None) or rationale_input.get("resolved_label", rec["type"])

        if llm_client:
            rationale = generate_rationale(
                llm_client,
                campaign_name=campaign_names.get(rec["campaign_id"], rec["campaign_id"]),
                metric=metric,
                root_cause_label=root_cause_label,
                confidence=rec["confidence_score"],
                recommended_action=rationale_input.get("note", ""),
                expected_impact_value=rec["expected_impact_value"],
                expected_impact_pct=rec["expected_impact_pct"],
            )
        else:
            rationale = FALLBACK_RATIONALE

        rec["rationale"] = rationale
        inserted.extend(db.insert("recommendations", [rec]))

    return {"anomalies_processed": len(unresolved), "recommendations_created": len(inserted)}
