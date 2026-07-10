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


def _load_type_stats(client) -> dict:
    return {r["type"]: r for r in client.table("recommendation_type_stats").select("*").execute().data}


def _has_pending_reallocation(client, campaign_id: str) -> bool:
    since = (date.today() - timedelta(days=DEDUP_WINDOW_DAYS)).isoformat()
    res = (
        client.table("recommendations")
        .select("rec_id")
        .eq("campaign_id", campaign_id)
        .eq("type", "budget")
        .is_("anomaly_id", "null")
        .eq("status", "pending")
        .gte("created_at", since)
        .execute()
    )
    return len(res.data) > 0


def run_recommendation() -> dict:
    client = db.get_client()
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()

    unresolved = client.table("anomalies").select("*").is_("root_cause_label", "null").execute().data

    # The cross-campaign ROAS-reallocation check runs over ALL campaigns (it
    # doesn't require an anomaly to fire), so pull broadly rather than scoping
    # to just the unresolved anomalies' campaigns.
    daily_metrics = pd.DataFrame(client.table("campaign_daily_metrics").select("*").gte("date", since).execute().data)
    campaigns = pd.DataFrame(client.table("campaigns").select("*").execute().data)
    budget_changes = pd.DataFrame(client.table("budget_change_log").select("*").execute().data)
    audience = pd.DataFrame(client.table("audience_segments").select("*").gte("date", since).execute().data)
    creatives = pd.DataFrame(client.table("creatives").select("*").gte("date", since).execute().data)

    if not unresolved and daily_metrics.empty:
        return {"anomalies_processed": 0, "recommendations_created": 0}

    resolved_anomalies, candidates = apply_root_causes(
        unresolved, daily_metrics, budget_changes, audience, creatives, campaigns
    )

    for a in resolved_anomalies:
        if a.get("root_cause_label") is not None:
            client.table("anomalies").update(
                {"root_cause_label": a["root_cause_label"], "root_cause_confidence": a["root_cause_confidence"]}
            ).eq("anomaly_id", a["anomaly_id"]).execute()

    candidates = [
        c
        for c in candidates
        if not (c["type"] == "budget" and c.get("anomaly_id") is None and _has_pending_reallocation(client, c["campaign_id"]))
    ]

    type_stats_rows = _load_type_stats(client)
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
    llm_client = build_client(settings.anthropic_api_key) if settings.anthropic_api_key else None

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
