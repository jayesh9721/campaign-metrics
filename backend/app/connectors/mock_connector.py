import hashlib
from datetime import date, timedelta

import numpy as np

from .base import PlatformConnector

DAYS = 30

CAMPAIGN_NAME_POOL = {
    "linkedin": [
        "ABM Enterprise Outreach",
        "Thought Leadership Push",
        "Lead Gen - Fintech Decision Makers",
        "Brand Awareness Q3",
        "Retargeting - Webinar Attendees",
    ],
    "other": [
        "Programmatic Display - Retail",
        "Native Content Amplification",
        "Connected TV Brand Push",
        "Affiliate Performance",
        "Podcast Sponsorship",
    ],
}
OBJECTIVE_POOL = {
    "linkedin": ["lead_generation", "brand_awareness", "website_conversions", "engagement"],
    "other": ["conversions", "reach", "traffic", "app_installs"],
}
BID_STRATEGY_POOL = ["lowest_cost", "cost_cap", "target_cost", "manual_bidding"]
STATUS_POOL = ["active", "active", "active", "paused"]  # weighted toward active
SEGMENT_POOL = ["18-24", "25-34", "35-44", "45-54", "55-64"]
CREATIVE_FORMAT_POOL = ["image", "video", "carousel"]
CHANGED_BY_POOL = ["auto_rule", "account_manager", "client_request"]


def _stable_seed(*parts: str) -> int:
    # hash() is process-salted in Python, so use md5 for a seed that's reproducible across runs
    digest = hashlib.md5("|".join(parts).encode()).hexdigest()
    return int(digest, 16) % (2**32)


class MockConnector(PlatformConnector):
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self._base_rng = np.random.default_rng(_stable_seed(platform, "base"))
        self._campaign_rngs: dict[str, np.random.Generator] = {}
        self._campaigns = self._build_campaigns()
        self._daily_metrics = self._build_daily_metrics()
        self._budget_changes = self._build_budget_changes()
        self._audience = self._build_audience()
        self._creatives = self._build_creatives()

    def _build_campaigns(self) -> list[dict]:
        name_pool = CAMPAIGN_NAME_POOL.get(self.platform, CAMPAIGN_NAME_POOL["other"])
        objective_pool = OBJECTIVE_POOL.get(self.platform, OBJECTIVE_POOL["other"])
        n = int(self._base_rng.integers(3, 6))

        campaigns = []
        for i in range(n):
            campaign_id = f"{self.platform}_camp_{i + 1}"
            rng = np.random.default_rng(_stable_seed(self.platform, campaign_id))
            self._campaign_rngs[campaign_id] = rng

            budget_type = "daily" if rng.random() < 0.7 else "lifetime"
            campaigns.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": name_pool[i % len(name_pool)],
                    "platform": self.platform,
                    "brand": "DemoBrand",
                    "account_id": f"{self.platform}_acct_001",
                    "objective": objective_pool[i % len(objective_pool)],
                    "bid_strategy": str(rng.choice(BID_STRATEGY_POOL)),
                    "status": str(rng.choice(STATUS_POOL)),
                    "start_date": date.today() - timedelta(days=int(rng.integers(60, 400))),
                    "budget_cap": round(float(rng.uniform(500, 5000)), 2),
                    "budget_type": budget_type,
                }
            )
        return campaigns

    def _build_daily_metrics(self) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=DAYS - 1)
        rows = []
        for camp in self._campaigns:
            cid = camp["campaign_id"]
            rng = self._campaign_rngs[cid]
            base_impressions = rng.uniform(8000, 40000)
            base_ctr = rng.uniform(0.008, 0.035)
            base_cpc = rng.uniform(0.8, 4.5)
            base_cvr = rng.uniform(0.02, 0.12)
            base_aov = rng.uniform(30, 250)

            anomaly_day = int(rng.integers(DAYS - 7, DAYS))  # anomaly lands in the last week
            anomaly_kind = str(rng.choice(["ctr_drop", "spend_spike"]))

            for day_idx in range(DAYS):
                d = start + timedelta(days=day_idx)
                impressions = max(1, int(base_impressions * (1 + rng.normal(0, 0.1))))
                ctr_draw = max(0.001, base_ctr * (1 + rng.normal(0, 0.15)))
                if day_idx == anomaly_day and anomaly_kind == "ctr_drop":
                    ctr_draw *= 0.25  # INJECTED ANOMALY: sudden CTR drop
                clicks = max(0, int(impressions * ctr_draw))

                cpc_draw = max(0.05, base_cpc * (1 + rng.normal(0, 0.12)))
                spend = round(clicks * cpc_draw, 2)
                if day_idx == anomaly_day and anomaly_kind == "spend_spike":
                    spend = round(spend * 3.5, 2)  # INJECTED ANOMALY: sudden spend spike

                cvr_draw = max(0.005, base_cvr * (1 + rng.normal(0, 0.2)))
                conversions = max(0, int(clicks * cvr_draw))
                revenue = round(conversions * base_aov * (1 + rng.normal(0, 0.1)), 2)

                rows.append(
                    {
                        "campaign_id": cid,
                        "date": d,
                        "impressions": impressions,
                        "clicks": clicks,
                        # ctr/cpc recomputed from clicks/spend so stored metrics reconcile internally
                        "ctr": round(clicks / impressions, 4) if impressions else None,
                        "cpc": round(spend / clicks, 4) if clicks else None,
                        "spend": spend,
                        "conversions": conversions,
                        "conversion_rate": round(conversions / clicks, 4) if clicks else None,
                        "revenue": revenue,
                        "roas": round(revenue / spend, 4) if spend else None,
                        "cpa": round(spend / conversions, 2) if conversions else None,
                        "frequency": round(float(rng.uniform(1.0, 3.5)), 2),
                    }
                )
        return rows

    def _build_budget_changes(self) -> list[dict]:
        rows = []
        for camp in self._campaigns:
            cid = camp["campaign_id"]
            rng = self._campaign_rngs[cid]
            current = camp["budget_cap"]
            for _ in range(int(rng.integers(1, 3))):
                change_date = date.today() - timedelta(days=int(rng.integers(1, 25)))
                old_budget = round(current * float(rng.uniform(0.7, 1.3)), 2)
                new_budget = round(old_budget * float(rng.uniform(0.8, 1.4)), 2)
                rows.append(
                    {
                        "campaign_id": cid,
                        "change_date": change_date,
                        "old_budget": old_budget,
                        "new_budget": new_budget,
                        "changed_by": str(rng.choice(CHANGED_BY_POOL)),
                    }
                )
                current = new_budget
        return rows

    def _build_audience(self) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=DAYS - 1)
        rows = []
        for camp in self._campaigns:
            cid = camp["campaign_id"]
            rng = self._campaign_rngs[cid]
            daily_for_camp = [m for m in self._daily_metrics if m["campaign_id"] == cid]

            n_segments = int(rng.integers(2, 4))
            segments = list(rng.choice(SEGMENT_POOL, size=n_segments, replace=False))
            shares = rng.dirichlet(np.ones(n_segments))

            for seg, share in zip(segments, shares):
                for day_idx in range(DAYS):
                    d = start + timedelta(days=day_idx)
                    metric = daily_for_camp[day_idx]
                    impressions = max(1, int(metric["impressions"] * share * (1 + rng.normal(0, 0.05))))
                    ctr = max(0.001, (metric["ctr"] or 0.01) * (1 + rng.normal(0, 0.2)))
                    cpa = metric["cpa"] * (1 + rng.normal(0, 0.2)) if metric["cpa"] else None
                    rows.append(
                        {
                            "campaign_id": cid,
                            "segment_id": str(seg),
                            "segment_name": str(seg),
                            "date": d,
                            "impressions": impressions,
                            "ctr": round(ctr, 4),
                            "cpa": round(cpa, 2) if cpa is not None else None,
                            "frequency": round(float(rng.uniform(1.0, 3.0)), 2),
                        }
                    )
        return rows

    def _build_creatives(self) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=DAYS - 1)
        rows = []
        for camp in self._campaigns:
            cid = camp["campaign_id"]
            rng = self._campaign_rngs[cid]

            n_creatives = int(rng.integers(2, 4))
            creative_ids = [f"{cid}_cr{i + 1}" for i in range(n_creatives)]
            formats = [str(rng.choice(CREATIVE_FORMAT_POOL)) for _ in range(n_creatives)]
            launch_dates = [
                camp["start_date"] + timedelta(days=int(rng.integers(0, 15))) for _ in range(n_creatives)
            ]
            shares_base = rng.dirichlet(np.ones(n_creatives))

            # inject one creative-fatigue CTR dip in the last week
            fatigue_idx = int(rng.integers(0, n_creatives))
            fatigue_day = int(rng.integers(DAYS - 7, DAYS))

            for day_idx in range(DAYS):
                d = start + timedelta(days=day_idx)
                noisy_shares = shares_base * (1 + rng.normal(0, 0.05, size=n_creatives))
                noisy_shares = np.clip(noisy_shares, 0.01, None)
                noisy_shares = noisy_shares / noisy_shares.sum()  # renormalize so spend_share sums to 1

                for i, crid in enumerate(creative_ids):
                    ctr = max(0.001, float(rng.uniform(0.008, 0.04)))
                    if i == fatigue_idx and day_idx == fatigue_day:
                        ctr *= 0.3  # INJECTED ANOMALY: creative fatigue CTR dip
                    rows.append(
                        {
                            "campaign_id": cid,
                            "creative_id": crid,
                            "launch_date": launch_dates[i],
                            "format": formats[i],
                            "date": d,
                            "ctr": round(ctr, 4),
                            "engagement_rate": round(float(rng.uniform(0.01, 0.08)), 4),
                            "spend_share": round(float(noisy_shares[i]), 4),
                        }
                    )
        return rows

    def fetch_campaigns(self) -> list[dict]:
        return [dict(c) for c in self._campaigns]

    def fetch_daily_metrics(self, since: date) -> list[dict]:
        return [dict(r) for r in self._daily_metrics if r["date"] >= since]

    def fetch_budget_changes(self, since: date) -> list[dict]:
        return [dict(r) for r in self._budget_changes if r["change_date"] >= since]

    def fetch_audience_data(self, since: date) -> list[dict]:
        return [dict(r) for r in self._audience if r["date"] >= since]

    def fetch_creative_data(self, since: date) -> list[dict]:
        return [dict(r) for r in self._creatives if r["date"] >= since]
