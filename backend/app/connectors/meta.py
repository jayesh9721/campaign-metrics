import json
from datetime import date, datetime

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.campaign import Campaign
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from .base import PlatformConnector

# Meta's action_type taxonomy varies by pixel/account setup; this allowlist covers
# the common purchase/lead events and is deliberately conservative over exhaustive.
CONVERSION_ACTION_TYPES = frozenset(
    {"offsite_conversion.fb_pixel_purchase", "purchase", "lead", "omni_purchase"}
)

# activity extra_data key pairs seen for budget-change events, in order of preference;
# Meta doesn't document this schema so we only trust an exact key-pair match.
BUDGET_EXTRA_DATA_KEYS = [
    ("old_value", "new_value"),
    ("daily_budget_old", "daily_budget_new"),
    ("old_budget", "new_budget"),
    ("lifetime_budget_old", "lifetime_budget_new"),
]


def _parse_meta_datetime(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").date()
    except ValueError:
        return None


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MetaConnector(PlatformConnector):
    def __init__(self, access_token: str, ad_account_id: str) -> None:
        self.ad_account_id = ad_account_id
        try:
            FacebookAdsApi.init(access_token=access_token)
        except Exception as e:
            raise RuntimeError(f"Meta API init failed: {e}") from e
        self.account = AdAccount(ad_account_id)

    def fetch_campaigns(self) -> list[dict]:
        fields = [
            Campaign.Field.id,
            Campaign.Field.name,
            Campaign.Field.objective,
            Campaign.Field.bid_strategy,
            Campaign.Field.status,
            Campaign.Field.start_time,
            Campaign.Field.daily_budget,
            Campaign.Field.lifetime_budget,
        ]
        try:
            cursor = self.account.get_campaigns(fields=fields)
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta get_campaigns failed: {e}") from e

        rows = []
        for c in cursor:  # Cursor auto-paginates on iteration
            daily_budget = c.get(Campaign.Field.daily_budget)
            lifetime_budget = c.get(Campaign.Field.lifetime_budget)
            if daily_budget is not None:
                budget_cap = _to_float(daily_budget) / 100
                budget_type = "daily"
            elif lifetime_budget is not None:
                budget_cap = _to_float(lifetime_budget) / 100
                budget_type = "lifetime"
            else:
                budget_cap = None
                budget_type = None

            rows.append(
                {
                    "campaign_id": c.get(Campaign.Field.id),
                    "campaign_name": c.get(Campaign.Field.name),
                    "platform": "meta",
                    "account_id": self.ad_account_id,
                    "objective": c.get(Campaign.Field.objective),
                    "bid_strategy": c.get(Campaign.Field.bid_strategy),
                    "status": (c.get(Campaign.Field.status) or "").lower() or None,
                    "start_date": _parse_meta_datetime(c.get(Campaign.Field.start_time)),
                    "budget_cap": budget_cap,
                    "budget_type": budget_type,
                }
            )
        return rows

    def fetch_daily_metrics(self, since: date) -> list[dict]:
        fields = [
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.date_start,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.spend,
            AdsInsights.Field.frequency,
            AdsInsights.Field.actions,
            AdsInsights.Field.action_values,
            AdsInsights.Field.purchase_roas,
        ]
        params = {
            "level": "campaign",
            "time_range": {"since": since.isoformat(), "until": date.today().isoformat()},
            "time_increment": 1,
        }
        try:
            cursor = self.account.get_insights(fields=fields, params=params)
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta get_insights (daily metrics) failed: {e}") from e

        rows = []
        for insight in cursor:
            actions = insight.get(AdsInsights.Field.actions) or []
            action_values = insight.get(AdsInsights.Field.action_values) or []
            conversions = sum(
                _to_float(a.get("value")) or 0.0
                for a in actions
                if a.get("action_type") in CONVERSION_ACTION_TYPES
            )
            revenue = sum(
                _to_float(a.get("value")) or 0.0
                for a in action_values
                if a.get("action_type") in CONVERSION_ACTION_TYPES
            )
            clicks = int(_to_float(insight.get(AdsInsights.Field.clicks)) or 0)
            spend = _to_float(insight.get(AdsInsights.Field.spend)) or 0.0
            impressions = int(_to_float(insight.get(AdsInsights.Field.impressions)) or 0)

            rows.append(
                {
                    "campaign_id": insight.get(AdsInsights.Field.campaign_id),
                    "date": date.fromisoformat(insight.get(AdsInsights.Field.date_start)),
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": _to_float(insight.get(AdsInsights.Field.ctr)),
                    "cpc": _to_float(insight.get(AdsInsights.Field.cpc)),
                    "spend": spend,
                    "conversions": conversions,
                    "conversion_rate": (conversions / clicks) if clicks else None,
                    "revenue": revenue,
                    "roas": (revenue / spend) if spend else None,
                    "cpa": (spend / conversions) if conversions else None,
                    "frequency": _to_float(insight.get(AdsInsights.Field.frequency)),
                }
            )
        return rows

    def fetch_budget_changes(self, since: date) -> list[dict]:
        # Meta has no single documented "budget history" endpoint; /activities is
        # best-effort and its extra_data schema for budget events is undocumented,
        # so any activity we can't cleanly parse old/new values from is skipped.
        fields = ["event_type", "event_time", "object_id", "extra_data", "actor_name"]
        params = {"since": since.isoformat()}
        try:
            cursor = self.account.get_activities(fields=fields, params=params)
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta get_activities (budget changes) failed: {e}") from e

        rows = []
        for activity in cursor:
            event_type = (activity.get("event_type") or "").lower()
            if "budget" not in event_type:
                continue
            raw_extra = activity.get("extra_data")
            if not raw_extra:
                continue
            try:
                extra = json.loads(raw_extra)
            except (TypeError, ValueError):
                continue

            old_budget, new_budget = self._extract_budget_values(extra)
            if old_budget is None or new_budget is None:
                continue  # can't confirm a clean old/new pair — skip rather than guess

            rows.append(
                {
                    "campaign_id": activity.get("object_id"),
                    "change_date": _parse_meta_datetime(activity.get("event_time")),
                    "old_budget": old_budget,
                    "new_budget": new_budget,
                    "changed_by": activity.get("actor_name"),
                }
            )
        return rows

    @staticmethod
    def _extract_budget_values(extra: dict) -> tuple[float | None, float | None]:
        for old_key, new_key in BUDGET_EXTRA_DATA_KEYS:
            if old_key in extra and new_key in extra:
                old_v = _to_float(extra[old_key])
                new_v = _to_float(extra[new_key])
                if old_v is None or new_v is None:
                    continue
                return old_v / 100, new_v / 100  # minor currency unit, same convention as budget_cap
        return None, None

    def fetch_audience_data(self, since: date) -> list[dict]:
        fields = [
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.date_start,
            AdsInsights.Field.impressions,
            AdsInsights.Field.ctr,
            AdsInsights.Field.frequency,
            AdsInsights.Field.spend,
            AdsInsights.Field.actions,
        ]
        params = {
            "level": "campaign",
            "time_range": {"since": since.isoformat(), "until": date.today().isoformat()},
            "time_increment": 1,
            "breakdowns": ["age"],  # simplest reliable breakdown available on every ad account
        }
        try:
            cursor = self.account.get_insights(fields=fields, params=params)
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta get_insights (audience data) failed: {e}") from e

        rows = []
        for insight in cursor:
            actions = insight.get(AdsInsights.Field.actions) or []
            conversions = sum(
                _to_float(a.get("value")) or 0.0
                for a in actions
                if a.get("action_type") in CONVERSION_ACTION_TYPES
            )
            spend = _to_float(insight.get(AdsInsights.Field.spend)) or 0.0
            age = insight.get("age")

            rows.append(
                {
                    "campaign_id": insight.get(AdsInsights.Field.campaign_id),
                    "segment_id": age,
                    "segment_name": age,
                    "date": date.fromisoformat(insight.get(AdsInsights.Field.date_start)),
                    "impressions": int(_to_float(insight.get(AdsInsights.Field.impressions)) or 0),
                    "ctr": _to_float(insight.get(AdsInsights.Field.ctr)),
                    "cpa": (spend / conversions) if conversions else None,
                    "frequency": _to_float(insight.get(AdsInsights.Field.frequency)),
                }
            )
        return rows

    def fetch_creative_data(self, since: date) -> list[dict]:
        fields = [
            AdsInsights.Field.ad_id,
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.date_start,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.spend,
        ]
        params = {
            "level": "ad",
            "time_range": {"since": since.isoformat(), "until": date.today().isoformat()},
            "time_increment": 1,
        }
        try:
            cursor = self.account.get_insights(fields=fields, params=params)
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta get_insights (creative data) failed: {e}") from e

        raw_rows = []
        for insight in cursor:
            raw_rows.append(
                {
                    "ad_id": insight.get(AdsInsights.Field.ad_id),
                    "campaign_id": insight.get(AdsInsights.Field.campaign_id),
                    "date": date.fromisoformat(insight.get(AdsInsights.Field.date_start)),
                    "ctr": _to_float(insight.get(AdsInsights.Field.ctr)),
                    "spend": _to_float(insight.get(AdsInsights.Field.spend)) or 0.0,
                }
            )

        spend_totals: dict[tuple[str, date], float] = {}
        for r in raw_rows:
            key = (r["campaign_id"], r["date"])
            spend_totals[key] = spend_totals.get(key, 0.0) + r["spend"]

        ad_metadata_cache: dict[str, dict] = {}
        rows = []
        for r in raw_rows:
            ad_id = r["ad_id"]
            if ad_id not in ad_metadata_cache:
                ad_metadata_cache[ad_id] = self._lookup_ad_metadata(ad_id)
            meta = ad_metadata_cache[ad_id]
            total_spend = spend_totals.get((r["campaign_id"], r["date"]), 0.0)

            rows.append(
                {
                    "campaign_id": r["campaign_id"],
                    "creative_id": ad_id,
                    "launch_date": meta["launch_date"],
                    "format": meta["format"],
                    "date": r["date"],
                    "ctr": r["ctr"],
                    "engagement_rate": None,  # not cheaply available from insights API — left null, not fabricated
                    "spend_share": (r["spend"] / total_spend) if total_spend else None,
                }
            )
        return rows

    @staticmethod
    def _lookup_ad_metadata(ad_id: str) -> dict:
        try:
            details = Ad(ad_id).api_get(fields=[Ad.Field.created_time, Ad.Field.creative])
        except FacebookRequestError as e:
            raise RuntimeError(f"Meta Ad.api_get failed for ad {ad_id}: {e}") from e

        launch_date = _parse_meta_datetime(details.get(Ad.Field.created_time))
        creative_ref = details.get(Ad.Field.creative)
        format_guess = "unknown"
        if creative_ref:
            try:
                # heuristic: no clean "format" field on AdCreative, so infer from which asset is present
                creative = AdCreative(creative_ref["id"]).api_get(
                    fields=[AdCreative.Field.image_url, AdCreative.Field.video_id]
                )
                if creative.get(AdCreative.Field.video_id):
                    format_guess = "video"
                elif creative.get(AdCreative.Field.image_url):
                    format_guess = "image"
            except FacebookRequestError:
                pass  # best-effort only — leave as 'unknown'
        return {"launch_date": launch_date, "format": format_guess}
