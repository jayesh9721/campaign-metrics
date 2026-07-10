"""Ingestion job (spec Part 12, step 1). Pulls from every connector and
upserts into the normalized schema. No connector-specific logic leaks past
this point - everything downstream reads the schema, not the platform."""
from __future__ import annotations

from datetime import date, timedelta

from app import db
from app.config import settings
from app.connectors.meta import MetaConnector
from app.connectors.mock_connector import MockConnector

# Scheduled runs (every 15-30 min per spec) only need to re-pull a short
# recent window - upserts on (campaign_id, date)-style keys make re-pulling
# the same days idempotent, so this doesn't need a precise last-run watermark.
DEFAULT_LOOKBACK_DAYS = 3


def get_connectors() -> list:
    connectors: list = []
    if settings.meta_access_token and settings.meta_ad_account_id:
        connectors.append(MetaConnector(settings.meta_access_token, settings.meta_ad_account_id))
    # LinkedIn / "other" have no real API access yet (spec Part 16) - mocked,
    # same schema, same polling cadence as the real connector.
    connectors.append(MockConnector("linkedin"))
    connectors.append(MockConnector("other"))
    return connectors


def _clean(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("campaign_id")]


def run_ingestion(since: date | None = None) -> dict:
    since = since or (date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    summary: dict[str, dict] = {}

    for connector in get_connectors():
        name = connector.__class__.__name__ + (f":{connector.platform}" if hasattr(connector, "platform") else "")

        campaigns = _clean(connector.fetch_campaigns())
        db.upsert("campaigns", campaigns, conflict_columns=["campaign_id"])

        daily_metrics = _clean(connector.fetch_daily_metrics(since))
        db.upsert("campaign_daily_metrics", daily_metrics, conflict_columns=["campaign_id", "date"])

        budget_changes = _clean(connector.fetch_budget_changes(since))
        db.insert_dedup(
            "budget_change_log", budget_changes,
            key_fields=["campaign_id", "change_date", "old_budget", "new_budget"],
        )

        audience = [r for r in _clean(connector.fetch_audience_data(since)) if r.get("segment_id") is not None]
        db.upsert("audience_segments", audience, conflict_columns=["campaign_id", "segment_id", "date"])

        creatives = [r for r in _clean(connector.fetch_creative_data(since)) if r.get("creative_id") is not None]
        db.upsert("creatives", creatives, conflict_columns=["campaign_id", "creative_id", "date"])

        summary[name] = {
            "campaigns": len(campaigns),
            "daily_metrics": len(daily_metrics),
            "budget_changes": len(budget_changes),
            "audience_rows": len(audience),
            "creative_rows": len(creatives),
        }

    return summary
