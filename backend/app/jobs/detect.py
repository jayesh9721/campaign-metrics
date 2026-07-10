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
# also avoids rewriting old anomaly rows (see the update_columns note below).
ACTIONABLE_WINDOW_DAYS = 2


def run_detection() -> dict:
    since = date.today() - timedelta(days=LOOKBACK_DAYS_FOR_BASELINE)
    rows = db.query(
        "SELECT * FROM campaign_daily_metrics WHERE date >= :since",
        {"since": since},
    )
    df = pd.DataFrame(rows)

    all_anomalies = detect_anomalies(df)
    cutoff = (date.today() - timedelta(days=ACTIONABLE_WINDOW_DAYS)).isoformat()
    recent = [a for a in all_anomalies if a["detected_date"] >= cutoff]

    # Only `severity` is updated on conflict - root_cause_label/
    # root_cause_confidence are never touched by the SET clause, so re-running
    # this job every cycle can't clobber root-cause work the recommendation
    # job already did on a still-active anomaly.
    db.upsert(
        "anomalies",
        recent,
        conflict_columns=["campaign_id", "metric", "detected_date"],
        update_columns=["severity"],
    )

    return {"anomalies_detected": len(recent)}
