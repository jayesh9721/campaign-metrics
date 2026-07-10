"""Rule-based root-cause attribution (spec Part 6).

Every branch below is a deterministic threshold on a real signal (spend/cap
ratio, impression trend, CPA slope, CTR streak, frequency slope). No LLM
involvement anywhere in this file — turning a finding into prose is
llm_rationale.py's job, not this one's.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---- thresholds/weights the spec leaves to judgment, documented here ------
BUDGET_CAP_RATIO_THRESHOLD = 0.95        # spend/budget_cap ratio considered "at cap"
BUDGET_CAP_LOW_RATIO_THRESHOLD = 0.80    # ratio considered "stable/low" -> rules OUT budget_cap
IMPRESSION_DECLINE_PCT = -0.05           # >=5% impression drop over the trailing 3 days counts as "declining"
ROAS_REALLOCATION_MULTIPLIER = 1.5       # A's ROAS > 1.5x B's ROAS triggers a reallocation candidate
REALLOCATION_SPEND_SHARE = 0.20          # suggest shifting 20% of the underperforming campaign's recent avg daily spend
CPA_SLOPE_RISING_THRESHOLD = 1e-3        # polyfit slope > this over trailing 7 days counts as "CPA rising";
                                          # a small epsilon above zero rather than exactly 0, so floating-point
                                          # noise on a perfectly flat CPA series can't register as "rising"
CTR_DECLINE_MIN_STREAK = 3               # 3+ consecutive CTR drops = creative-fatigue candidate
FREQUENCY_RISING_MIN_SLOPE = 1e-3        # same epsilon-above-zero rationale, for segment frequency slope

# Fixed confidence per rule firing. Higher when every condition is cleanly
# met; lower when the attribution involves an extra inferential step
# (cross-campaign comparison, re-attributing creative_fatigue to audience_fatigue).
CONF_BUDGET_CAP = 0.8
CONF_REALLOCATION = 0.7
CONF_BIDDING = 0.75
CONF_CREATIVE_FATIGUE = 0.75
CONF_AUDIENCE_FATIGUE = 0.7


def _slope(values: pd.Series) -> float:
    """Simple linear trend via numpy.polyfit — chosen over a rolling-mean
    comparison because we just need one trend number (rising/falling) per window."""
    y = values.dropna().to_numpy(dtype=float)
    if len(y) < 2:
        return 0.0
    x = np.arange(len(y), dtype=float)
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def _with_ratio_and_decline(daily_metrics_df: pd.DataFrame, campaigns_df: pd.DataFrame) -> pd.DataFrame:
    df = daily_metrics_df.merge(
        campaigns_df[["campaign_id", "budget_cap", "brand"]], on="campaign_id", how="left"
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["campaign_id", "date"])
    df["ratio"] = df["spend"] / df["budget_cap"].replace(0, np.nan)
    # 3-day trailing "declining impressions" signal: this day vs. 2 days prior
    df["impressions_pct_change_3d"] = df.groupby("campaign_id")["impressions"].pct_change(periods=2)
    return df


def apply_root_causes(
    anomalies: list[dict],
    daily_metrics_df: pd.DataFrame,
    budget_change_log_df: pd.DataFrame,
    audience_segments_df: pd.DataFrame,
    creatives_df: pd.DataFrame,
    campaigns_df: pd.DataFrame,
) -> tuple[list[dict], list[dict]]:
    anomalies = [dict(a) for a in anomalies]  # don't mutate the caller's dicts in place
    candidates: list[dict] = []

    if daily_metrics_df.empty or campaigns_df.empty:
        return anomalies, candidates

    metrics_df = _with_ratio_and_decline(daily_metrics_df, campaigns_df)

    # ---- per (campaign, date) "is budget capped today" lookup -------------
    budget_capped_dates: dict[tuple[str, pd.Timestamp], bool] = {}
    for _, row in metrics_df.iterrows():
        is_capped = (
            pd.notna(row["ratio"])
            and row["ratio"] > BUDGET_CAP_RATIO_THRESHOLD
            and pd.notna(row["impressions_pct_change_3d"])
            and row["impressions_pct_change_3d"] < IMPRESSION_DECLINE_PCT
        )
        budget_capped_dates[(row["campaign_id"], row["date"])] = bool(is_capped)

    # ---- per-campaign "most recent" ratio / capped flag / ROAS / spend ----
    latest_capped: dict[str, bool] = {}
    latest_ratio: dict[str, float] = {}
    recent_roas: dict[str, float] = {}
    recent_spend: dict[str, float] = {}
    for campaign_id, g in metrics_df.groupby("campaign_id"):
        g = g.sort_values("date")
        last = g.iloc[-1]
        latest_ratio[campaign_id] = float(last["ratio"]) if pd.notna(last["ratio"]) else np.nan
        latest_capped[campaign_id] = bool(
            pd.notna(last["ratio"]) and last["ratio"] > BUDGET_CAP_RATIO_THRESHOLD
        )
        trailing7 = g.tail(7)
        recent_roas[campaign_id] = (
            float(trailing7["roas"].mean()) if trailing7["roas"].notna().any() else np.nan
        )
        recent_spend[campaign_id] = (
            float(trailing7["spend"].mean()) if trailing7["spend"].notna().any() else np.nan
        )

    # ---- budget monitoring: attach budget_cap root cause to matching anomalies ----
    for anomaly in anomalies:
        if anomaly.get("root_cause_label") is not None:
            continue
        key = (anomaly["campaign_id"], pd.to_datetime(anomaly["detected_date"]))
        if budget_capped_dates.get(key):
            anomaly["root_cause_label"] = "budget_cap"
            anomaly["root_cause_confidence"] = CONF_BUDGET_CAP

    # ---- budget monitoring: cross-campaign ROAS reallocation (same brand) ----
    brand_map = campaigns_df.set_index("campaign_id")["brand"].to_dict()
    campaigns_by_brand: dict[str, list[str]] = {}
    for cid, brand in brand_map.items():
        campaigns_by_brand.setdefault(brand, []).append(cid)

    for brand, campaign_ids in campaigns_by_brand.items():
        for a_id in campaign_ids:
            for b_id in campaign_ids:
                if a_id == b_id:
                    continue
                roas_a, roas_b = recent_roas.get(a_id), recent_roas.get(b_id)
                if pd.isna(roas_a) or pd.isna(roas_b) or roas_b <= 0:
                    continue
                if roas_a > ROAS_REALLOCATION_MULTIPLIER * roas_b and not latest_capped.get(b_id, False):
                    spend_b = recent_spend.get(b_id) or 0.0
                    candidates.append(
                        {
                            "type": "budget",
                            "campaign_id": b_id,
                            "anomaly_id": None,
                            "receiving_campaign_id": a_id,
                            "amount_shifted": spend_b * REALLOCATION_SPEND_SHARE,
                            "receiving_campaign_roas": roas_a,
                            "losing_campaign_roas": roas_b,
                            "recent_spend": spend_b,
                            "brand": brand,
                            "confidence": CONF_REALLOCATION,
                            "rationale_input": {
                                "reason": "cross_campaign_roas_gap",
                                "note": (
                                    f"Campaign {a_id} ROAS ({roas_a:.2f}) is more than "
                                    f"{ROAS_REALLOCATION_MULTIPLIER}x campaign {b_id} ROAS ({roas_b:.2f}); "
                                    f"{b_id} is not budget-capped, so shifting spend to {a_id} is viable."
                                ),
                            },
                        }
                    )

    # ---- bidding monitoring ----
    for campaign_id, g in metrics_df.groupby("campaign_id"):
        g = g.sort_values("date")
        trailing7 = g.tail(7)
        if trailing7["cpa"].notna().sum() < 2:
            continue

        cpa_slope = _slope(trailing7["cpa"])
        last_ratio = latest_ratio.get(campaign_id, np.nan)
        budget_cap_ruled_out = pd.notna(last_ratio) and last_ratio < BUDGET_CAP_LOW_RATIO_THRESHOLD
        cpa_rising = cpa_slope > CPA_SLOPE_RISING_THRESHOLD

        # NOTE: schema has no dedicated bid-strategy-change history table
        # (budget_change_log tracks budget changes only, not bid_strategy) —
        # "days since last bid_strategy change" is unavailable, so that
        # sub-condition is treated as unknown/skipped (never blocks) per the
        # spec's own escape valve. Consequence: the learning_phase branch of
        # this rule can't be evaluated from bidding-monitor data alone.
        if cpa_rising and budget_cap_ruled_out:
            matching_anomalies = [
                a
                for a in anomalies
                if a["campaign_id"] == campaign_id and a["metric"] == "cpa" and a.get("root_cause_label") is None
            ]
            for a in matching_anomalies:
                a["root_cause_label"] = "bidding"
                a["root_cause_confidence"] = CONF_BIDDING

            candidates.append(
                {
                    "type": "bidding",
                    "campaign_id": campaign_id,
                    "anomaly_id": matching_anomalies[0].get("anomaly_id") if matching_anomalies else None,
                    "recent_cpa_slope": cpa_slope,
                    "recent_spend": recent_spend.get(campaign_id, 0.0),
                    "confidence": CONF_BIDDING,
                    "rationale_input": {
                        "reason": "cpa_rising_not_budget_capped",
                        "note": (
                            f"CPA is trending up (slope={cpa_slope:.3f}/day) over the trailing 7 days while "
                            f"spend/budget_cap ratio is low ({last_ratio:.2f}), ruling out a budget cap."
                        ),
                    },
                }
            )

    # ---- creative monitoring ----
    if not creatives_df.empty:
        creatives_sorted = creatives_df.copy()
        creatives_sorted["date"] = pd.to_datetime(creatives_sorted["date"])
        for creative_id, g in creatives_sorted.sort_values("date").groupby("creative_id"):
            g = g.sort_values("date")
            campaign_id = g["campaign_id"].iloc[0]

            # longest streak of consecutive CTR declines
            streak = 0
            max_streak = 0
            for d in g["ctr"].diff():
                if pd.notna(d) and d < 0:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0
            if max_streak < CTR_DECLINE_MIN_STREAK:
                continue

            # cross-check: is frequency rising on this campaign's audience segments
            # over the same window? If so, the overexposure is on the audience, not
            # the creative, per the spec's explicit instruction to re-label.
            freq_slope = 0.0
            if not audience_segments_df.empty:
                seg = audience_segments_df[audience_segments_df["campaign_id"] == campaign_id].copy()
                if not seg.empty:
                    seg["date"] = pd.to_datetime(seg["date"])
                    seg = seg.sort_values("date").tail(len(g))
                    freq_slope = _slope(seg["frequency"])
            audience_driven = freq_slope > FREQUENCY_RISING_MIN_SLOPE

            label = "audience_fatigue" if audience_driven else "creative_fatigue"
            confidence = CONF_AUDIENCE_FATIGUE if audience_driven else CONF_CREATIVE_FATIGUE

            for a in anomalies:
                if a["campaign_id"] == campaign_id and a["metric"] == "ctr" and a.get("root_cause_label") is None:
                    a["root_cause_label"] = label
                    a["root_cause_confidence"] = confidence

            candidates.append(
                {
                    "type": "creative",
                    "campaign_id": campaign_id,
                    "anomaly_id": None,
                    "creative_id": creative_id,
                    "recent_spend": recent_spend.get(campaign_id, 0.0),
                    "confidence": confidence,
                    "rationale_input": {
                        "resolved_label": label,
                        "note": (
                            f"Creative {creative_id} CTR declined for {max_streak} consecutive checks; "
                            + (
                                f"segment frequency on this campaign is also rising (slope={freq_slope:.4f}), "
                                "pointing to audience overexposure rather than the creative itself — labeled "
                                "audience_fatigue, but still flagging this creative for refresh."
                                if audience_driven
                                else "no corresponding rise in segment frequency, consistent with creative_fatigue."
                            )
                        ),
                    },
                }
            )

    return anomalies, candidates
