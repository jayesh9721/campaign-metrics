from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.config import settings
from app.jobs.detect import run_detection
from app.jobs.ingest import run_ingestion
from app.jobs.recommend import run_recommendation

app = FastAPI(title="AI Campaign Optimization Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon demo scope; tighten to the deployed frontend origin for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQL snippet ranking severity so "ORDER BY ... severity DESC" reads as
# high > medium > low rather than alphabetically ("medium" > "low" > "high").
_SEVERITY_RANK_SQL = "CASE severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END"

# An anomaly is "open" until a recommendation linked to it has been reviewed
# (approved/rejected) - a still-pending or nonexistent recommendation leaves
# it open.
_OPEN_ANOMALY_SQL = """NOT EXISTS (
    SELECT 1 FROM recommendations r
    WHERE r.anomaly_id = a.anomaly_id AND r.status != 'pending'
)"""


def _check_pipeline_secret(x_pipeline_secret: str | None) -> None:
    if not settings.pipeline_trigger_secret:
        return  # secret not configured (local dev) - skip the check
    if x_pipeline_secret != settings.pipeline_trigger_secret:
        raise HTTPException(status_code=401, detail="invalid pipeline trigger secret")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/jobs/ingest")
def jobs_ingest(x_pipeline_secret: str | None = Header(default=None)) -> dict:
    _check_pipeline_secret(x_pipeline_secret)
    return run_ingestion()


@app.post("/jobs/detect")
def jobs_detect(x_pipeline_secret: str | None = Header(default=None)) -> dict:
    _check_pipeline_secret(x_pipeline_secret)
    return run_detection()


@app.post("/jobs/recommend")
def jobs_recommend(x_pipeline_secret: str | None = Header(default=None)) -> dict:
    _check_pipeline_secret(x_pipeline_secret)
    return run_recommendation()


class ReviewRequest(BaseModel):
    status: str  # 'approved' | 'rejected'
    reviewed_by: str


@app.post("/recommendations/{rec_id}/review")
def review_recommendation(rec_id: int, body: ReviewRequest) -> dict:
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")

    existing = db.query("SELECT * FROM recommendations WHERE rec_id = :rec_id", {"rec_id": rec_id})
    if not existing:
        raise HTTPException(status_code=404, detail="recommendation not found")
    rec = existing[0]

    db.execute(
        """
        UPDATE recommendations
        SET status = :status, reviewed_by = :reviewed_by, reviewed_at = :reviewed_at
        WHERE rec_id = :rec_id
        """,
        {
            "status": body.status,
            "reviewed_by": body.reviewed_by,
            "reviewed_at": datetime.now(timezone.utc),
            "rec_id": rec_id,
        },
    )

    # Human-in-the-loop feedback (spec Part 9): nudge this type's running
    # approval/rejection counts so the next recommend job's adjust_confidence
    # call reflects observed behavior.
    stats_res = db.query(
        "SELECT * FROM recommendation_type_stats WHERE type = :type", {"type": rec["type"]}
    )
    if stats_res:
        stats = stats_res[0]
        field = "approved_count" if body.status == "approved" else "rejected_count"
        db.execute(
            f"""
            UPDATE recommendation_type_stats
            SET {field} = :count, updated_at = :updated_at
            WHERE type = :type
            """,
            {"count": stats[field] + 1, "updated_at": datetime.now(timezone.utc), "type": rec["type"]},
        )

    return {"rec_id": rec_id, "status": body.status}


# ---------------------------------------------------------------------------
# Read endpoints for the frontend (Cloud SQL has no public REST/realtime
# layer the way Supabase did, so the frontend now fetches through this API).
# ---------------------------------------------------------------------------


@app.get("/campaigns")
def list_campaigns() -> list[dict]:
    return db.query("SELECT * FROM campaigns")


@app.get("/campaigns/{campaign_id}/daily-metrics")
def campaign_daily_metrics(campaign_id: str, days: int = 30) -> list[dict]:
    since = date.today() - timedelta(days=days)
    return db.query(
        """
        SELECT * FROM campaign_daily_metrics
        WHERE campaign_id = :campaign_id AND date >= :since
        ORDER BY date ASC
        """,
        {"campaign_id": campaign_id, "since": since},
    )


@app.get("/anomalies")
def list_anomalies(
    days: int = 30,
    severity: str = "",
    metric: str = "",
    status: str = "open",
) -> list[dict]:
    if status not in ("open", "all"):
        raise HTTPException(status_code=400, detail="status must be 'open' or 'all'")

    since = date.today() - timedelta(days=days)
    clauses = ["a.detected_date >= :since"]
    params: dict = {"since": since}

    if severity:
        clauses.append("a.severity = :severity")
        params["severity"] = severity
    if metric:
        clauses.append("a.metric = :metric")
        params["metric"] = metric
    if status == "open":
        clauses.append(_OPEN_ANOMALY_SQL)

    where = " AND ".join(clauses)
    sql = f"""
        SELECT a.*, c.campaign_name, c.platform, c.brand
        FROM anomalies a
        JOIN campaigns c ON c.campaign_id = a.campaign_id
        WHERE {where}
        ORDER BY a.detected_date DESC, {_SEVERITY_RANK_SQL.replace('severity', 'a.severity')} DESC
    """
    return db.query(sql, params)


@app.get("/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: int) -> dict:
    rows = db.query(
        """
        SELECT a.*, c.campaign_name, c.platform, c.brand
        FROM anomalies a
        JOIN campaigns c ON c.campaign_id = a.campaign_id
        WHERE a.anomaly_id = :anomaly_id
        """,
        {"anomaly_id": anomaly_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="anomaly not found")
    anomaly = rows[0]

    # Trailing 30 days ending at the anomaly's own detected_date (not
    # "today") so the chart shows the baseline window the anomaly was
    # actually flagged against, even if the anomaly has been open for a
    # while since then.
    until = anomaly["detected_date"]
    since = until - timedelta(days=30)
    anomaly["daily_metrics"] = db.query(
        """
        SELECT * FROM campaign_daily_metrics
        WHERE campaign_id = :campaign_id AND date >= :since AND date <= :until
        ORDER BY date ASC
        """,
        {"campaign_id": anomaly["campaign_id"], "since": since, "until": until},
    )
    anomaly["recommendations"] = db.query(
        "SELECT * FROM recommendations WHERE anomaly_id = :anomaly_id ORDER BY priority_score DESC",
        {"anomaly_id": anomaly_id},
    )
    return anomaly


@app.get("/recommendations")
def list_recommendations(
    status: str = "",
    type: str = Query(default="", alias="type"),
) -> list[dict]:
    clauses = []
    params: dict = {}
    if status:
        clauses.append("r.status = :status")
        params["status"] = status
    if type:
        clauses.append("r.type = :type")
        params["type"] = type

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT r.*, c.campaign_name, c.platform, c.brand
        FROM recommendations r
        JOIN campaigns c ON c.campaign_id = r.campaign_id
        {where}
        ORDER BY r.priority_score DESC
    """
    return db.query(sql, params)


@app.get("/dashboard-summary")
def dashboard_summary() -> dict:
    since_7d = date.today() - timedelta(days=7)

    severity_counts_rows = db.query(
        f"""
        SELECT a.severity, COUNT(*) AS cnt
        FROM anomalies a
        WHERE a.detected_date >= :since AND {_OPEN_ANOMALY_SQL}
        GROUP BY a.severity
        """,
        {"since": since_7d},
    )
    severity_counts = {r["severity"]: r["cnt"] for r in severity_counts_rows}
    open_high = severity_counts.get("high", 0)
    open_medium = severity_counts.get("medium", 0)
    active_alert_count = sum(severity_counts.values())

    health_score = 100 - (open_high * 10) - (open_medium * 4)
    health_score = max(0, min(100, health_score))

    pending_action_count = db.query(
        "SELECT COUNT(*) AS cnt FROM recommendations WHERE status = 'pending'"
    )[0]["cnt"]

    # "Most recent row per campaign" via DISTINCT ON (Postgres extension);
    # if a campaign has two rows on the exact same latest date, DISTINCT ON
    # picks whichever Postgres encounters first for that campaign_id, since
    # we only order by date within the window - an acceptable tie-break for
    # a dashboard tile, but worth knowing.
    top_roas_rows = db.query(
        """
        WITH latest AS (
            SELECT DISTINCT ON (campaign_id) campaign_id, date, roas
            FROM campaign_daily_metrics
            ORDER BY campaign_id, date DESC
        )
        SELECT l.campaign_id, c.campaign_name, l.roas, l.date
        FROM latest l
        JOIN campaigns c ON c.campaign_id = l.campaign_id
        WHERE l.roas IS NOT NULL
        ORDER BY l.roas DESC
        LIMIT 1
        """
    )
    top_roas_campaign = top_roas_rows[0] if top_roas_rows else None

    # Not scoped to the same 7-day window as health_score/active_alert_count
    # above - "most urgent" is meant to surface the single worst open
    # anomaly regardless of age, since an anomaly stays open indefinitely
    # until reviewed.
    urgent_rows = db.query(
        f"""
        SELECT a.*, c.campaign_name
        FROM anomalies a
        JOIN campaigns c ON c.campaign_id = a.campaign_id
        WHERE {_OPEN_ANOMALY_SQL}
        ORDER BY {_SEVERITY_RANK_SQL.replace('severity', 'a.severity')} DESC, a.detected_date DESC
        LIMIT 1
        """
    )
    most_urgent_anomaly = None
    if urgent_rows:
        most_urgent_anomaly = urgent_rows[0]
        top_rec_rows = db.query(
            """
            SELECT rec_id, rationale, priority_score
            FROM recommendations
            WHERE anomaly_id = :anomaly_id
            ORDER BY priority_score DESC
            LIMIT 1
            """,
            {"anomaly_id": most_urgent_anomaly["anomaly_id"]},
        )
        most_urgent_anomaly["top_recommendation"] = top_rec_rows[0] if top_rec_rows else None

    time_saved_hours = (active_alert_count * 15) / 60.0

    reviewed_counts_rows = db.query(
        "SELECT status, COUNT(*) AS cnt FROM recommendations WHERE status IN ('approved', 'rejected') GROUP BY status"
    )
    reviewed_counts = {r["status"]: r["cnt"] for r in reviewed_counts_rows}
    approved = reviewed_counts.get("approved", 0)
    rejected = reviewed_counts.get("rejected", 0)
    total_reviewed = approved + rejected
    approval_rate_pct = (approved / total_reviewed * 100) if total_reviewed > 0 else None

    return {
        "health_score": health_score,
        "active_alert_count": active_alert_count,
        "pending_action_count": pending_action_count,
        "top_roas_campaign": top_roas_campaign,
        "most_urgent_anomaly": most_urgent_anomaly,
        "time_saved_hours": time_saved_hours,
        "approval_rate_pct": approval_rate_pct,
    }
