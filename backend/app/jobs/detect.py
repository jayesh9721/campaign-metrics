"""Anomaly detection job (spec Part 12, step 2). Reads campaign_daily_metrics,
writes anomalies. Runs after ingestion completes."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app import db
from app.engine.anomaly_detection import detect_anomalies

# Needs enough history for the weekday-baseline window (8 same-weekday
# occurrences ~ 56 calendar days minimum) - padded generously.
LOOKBACK_DAYS_FOR_BASELINE = 120

# Only anomalies from the last couple of days are actionable each run; this
# also avoids rewriting old anomaly rows (see the field-omission note below).
ACTIONABLE_WINDOW_DAYS = 2


def run_detection() -> dict:
    client = db.get_client()
    since = (date.today() - timedelta(days=LOOKBACK_DAYS_FOR_BASELINE)).isoformat()
    res = client.table("campaign_daily_metrics").select("*").gte("date", since).execute()
    df = pd.DataFrame(res.data)

    all_anomalies = detect_anomalies(df)
    cutoff = (date.today() - timedelta(days=ACTIONABLE_WINDOW_DAYS)).isoformat()
    recent = [a for a in all_anomalies if a["detected_date"] >= cutoff]

    # Omit root_cause_label/root_cause_confidence entirely from the upsert
    # payload (rather than sending them as None) - Supabase/PostgREST's
    # merge-duplicates upsert only touches columns present in the payload, so
    # this preserves root-cause work the recommendation job already did on a
    # still-active anomaly instead of resetting it to null every 15 minutes.
    rows = [{k: v for k, v in a.items() if k not in ("root_cause_label", "root_cause_confidence")} for a in recent]
    db.upsert("anomalies", rows, on_conflict="campaign_id,metric,detected_date")

    return {"anomalies_detected": len(recent)}
