"""Manual CSV import - acts as a user-supplied connector. Maps a spreadsheet
of campaign performance into the same normalized schema every real connector
writes to (spec Part 3: nothing downstream cares which connector produced a
row), so anomaly detection/root cause/recommendations run over uploaded data
exactly the same way they run over Meta or mocked data."""
from __future__ import annotations

import io

import pandas as pd

from app import db

REQUIRED_COLUMNS = ["campaign_id", "campaign_name", "platform", "date", "impressions", "clicks", "spend"]

CAMPAIGN_COLUMNS = [
    "campaign_id", "campaign_name", "platform", "brand", "account_id",
    "objective", "bid_strategy", "status", "start_date", "budget_cap", "budget_type",
]
METRIC_NUMERIC_COLUMNS = [
    "impressions", "clicks", "spend", "conversions", "revenue", "frequency",
    "ctr", "cpc", "conversion_rate", "roas", "cpa",
]


class CsvImportError(Exception):
    pass


def _to_float(value) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_csv_import(file_content: bytes) -> dict:
    try:
        df = pd.read_csv(io.BytesIO(file_content))
    except Exception as e:
        raise CsvImportError(f"Could not parse file as CSV: {e}") from e

    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CsvImportError(f"Missing required column(s): {', '.join(missing)}")

    for col in METRIC_NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date

    bad_rows = int(df["date"].isna().sum()) + int(df["campaign_id"].isna().sum())
    df = df.dropna(subset=["date", "campaign_id"])

    # Derive whatever metrics the sheet didn't already provide - same formulas
    # the real connectors use, so uploaded data behaves identically downstream.
    impressions = df["impressions"].apply(_to_float)
    clicks = df["clicks"].apply(_to_float)
    spend = df["spend"].apply(_to_float)
    conversions = df["conversions"].apply(_to_float)
    revenue = df["revenue"].apply(_to_float)

    df["ctr"] = df["ctr"].apply(_to_float).where(
        df["ctr"].notna(), [
            (c / i * 100) if i else None for c, i in zip(clicks, impressions)
        ]
    )
    df["cpc"] = df["cpc"].apply(_to_float).where(
        df["cpc"].notna(), [(s / c) if c else None for s, c in zip(spend, clicks)]
    )
    df["conversion_rate"] = df["conversion_rate"].apply(_to_float).where(
        df["conversion_rate"].notna(), [(cv / c) if c else None for cv, c in zip(conversions, clicks)]
    )
    df["roas"] = df["roas"].apply(_to_float).where(
        df["roas"].notna(), [(r / s) if s else None for r, s in zip(revenue, spend)]
    )
    df["cpa"] = df["cpa"].apply(_to_float).where(
        df["cpa"].notna(), [(s / cv) if cv else None for s, cv in zip(spend, conversions)]
    )

    if "platform" in df.columns:
        df["platform"] = df["platform"].fillna("csv_upload").replace("", "csv_upload")

    campaign_rows = (
        df[[c for c in CAMPAIGN_COLUMNS if c in df.columns]]
        .drop_duplicates(subset=["campaign_id"], keep="first")
        .to_dict("records")
    )
    campaign_rows = [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in campaign_rows]

    metric_columns = ["campaign_id", "date"] + METRIC_NUMERIC_COLUMNS
    metric_rows = (
        df[[c for c in metric_columns if c in df.columns]]
        .drop_duplicates(subset=["campaign_id", "date"], keep="last")
        .to_dict("records")
    )
    metric_rows = [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in metric_rows]

    db.upsert("campaigns", campaign_rows, on_conflict="campaign_id")
    db.upsert("campaign_daily_metrics", metric_rows, on_conflict="campaign_id,date")

    return {
        "campaigns": len(campaign_rows),
        "daily_metrics": len(metric_rows),
        "rows_skipped": bad_rows,
    }
