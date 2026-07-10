"""Rule-based anomaly detection over campaign_daily_metrics (spec Part 7).

Deterministic/statistical only: rolling weekday-adjusted mean/std + a fixed
sigma threshold. No LLM involvement anywhere in this file.
"""
from __future__ import annotations

import pandas as pd

METRICS = ["ctr", "cpa", "roas", "spend"]

# Number of trailing same-weekday occurrences used as the comparison baseline
# for a given date. We compare "this Monday" against the last WEEKDAY_WINDOW
# Mondays rather than a raw trailing-N-day average, so weekday/weekend mix
# shifts don't masquerade as anomalies. 8 occurrences (~8 weeks of history for
# that weekday) is our stand-in for the spec's "14-day-ish window" expressed in
# weekday-count terms rather than calendar days — the spec explicitly leaves
# the exact number to judgment.
WEEKDAY_WINDOW = 8
MIN_PERIODS = 3  # need a few prior samples before std is meaningful

Z_MEDIUM = 2.0
Z_HIGH = 3.0


def _weekday_baseline(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Trailing (excludes the current row) same-weekday mean/std, series must
    already be ordered by date for a single campaign+metric+weekday group."""
    shifted = series.shift(1)
    mean = shifted.rolling(window=WEEKDAY_WINDOW, min_periods=MIN_PERIODS).mean()
    std = shifted.rolling(window=WEEKDAY_WINDOW, min_periods=MIN_PERIODS).std()
    return mean, std


def detect_anomalies(daily_metrics_df: pd.DataFrame) -> list[dict]:
    """Groups internally by campaign_id; returns anomalies table-shaped dicts
    with root_cause_label/root_cause_confidence left as None (root_cause.py's job)."""
    if daily_metrics_df.empty:
        return []

    df = daily_metrics_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["campaign_id", "date"]).reset_index(drop=True)
    df["_weekday"] = df["date"].dt.weekday

    anomalies: list[dict] = []

    for campaign_id, campaign_df in df.groupby("campaign_id", sort=False):
        for metric in METRICS:
            if metric not in campaign_df.columns:
                continue

            metric_df = campaign_df[["date", "_weekday", metric]].copy()

            baseline_mean = pd.Series(index=metric_df.index, dtype=float)
            baseline_std = pd.Series(index=metric_df.index, dtype=float)
            for _, weekday_group in metric_df.groupby("_weekday"):
                weekday_group = weekday_group.sort_values("date")
                mean, std = _weekday_baseline(weekday_group[metric])
                baseline_mean.loc[weekday_group.index] = mean.to_numpy()
                baseline_std.loc[weekday_group.index] = std.to_numpy()

            metric_df["_baseline_mean"] = baseline_mean
            metric_df["_baseline_std"] = baseline_std
            metric_df = metric_df.sort_values("date")

            for _, row in metric_df.iterrows():
                value = row[metric]
                mean = row["_baseline_mean"]
                std = row["_baseline_std"]
                # guard: not enough history yet, or a zero-variance baseline -> no anomaly (not a division error)
                if pd.isna(value) or pd.isna(mean) or pd.isna(std) or std == 0:
                    continue

                z = abs(value - mean) / std
                if z > Z_HIGH:
                    severity = "high"
                elif z > Z_MEDIUM:
                    severity = "medium"
                else:
                    # <=2 sigma is not flagged by this rule; 'low' severity is reserved
                    # for a future, lower-threshold rule the spec leaves room for.
                    continue

                anomalies.append(
                    {
                        "campaign_id": campaign_id,
                        "metric": metric,
                        "detected_date": row["date"].date().isoformat(),
                        "severity": severity,
                        "root_cause_label": None,
                        "root_cause_confidence": None,
                    }
                )

    return anomalies
