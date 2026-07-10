from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
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

    client = db.get_client()
    existing = client.table("recommendations").select("*").eq("rec_id", rec_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="recommendation not found")
    rec = existing[0]

    client.table("recommendations").update(
        {
            "status": body.status,
            "reviewed_by": body.reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("rec_id", rec_id).execute()

    # Human-in-the-loop feedback (spec Part 9): nudge this type's running
    # approval/rejection counts so the next recommend job's adjust_confidence
    # call reflects observed behavior.
    stats_res = client.table("recommendation_type_stats").select("*").eq("type", rec["type"]).execute().data
    if stats_res:
        stats = stats_res[0]
        field = "approved_count" if body.status == "approved" else "rejected_count"
        client.table("recommendation_type_stats").update(
            {field: stats[field] + 1, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("type", rec["type"]).execute()

    return {"rec_id": rec_id, "status": body.status}
