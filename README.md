# AI Campaign Optimization Copilot

Built against `PROJECT_BUILD_SPEC.md`. See that file for the full spec this implements.

Runs entirely on GCP: Cloud SQL (Postgres) for data, Cloud Run for both the
FastAPI backend and Next.js frontend, Cloud Scheduler for automation.

## Architecture

```
connectors (Meta real / LinkedIn+other mocked / Google Ads stub)
        |
        v
  normalized schema (Cloud SQL for Postgres, sql/schema.sql)
        |
        v
anomaly detection -> root cause engine -> recommendation engine -> Claude rationale
        |                                                          (via OpenRouter)
        v
FastAPI job endpoints (backend/app/jobs/*)  <-- triggered every 15 min by
        |                                       Cloud Scheduler (HTTP target)
        v
Next.js frontend (polls FastAPI REST endpoints every 20s - no direct DB access
        from the browser, since Cloud SQL has no public query layer)
```

Everything above the connector layer reads/writes only the normalized schema — no module calls a platform API directly (spec Part 3).

## One-time GCP setup (run in Cloud Shell)

```bash
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com

# Cloud SQL instance (smallest tier - fine for a hackathon demo, resize/upgrade for real load)
gcloud sql instances create copilot-db \
  --database-version=POSTGRES_15 --tier=db-f1-micro --region=us-central1

gcloud sql databases create campaign_copilot --instance=copilot-db

gcloud sql users create copilot_app --instance=copilot-db --password=<CHOOSE_A_PASSWORD>

# Grab the instance connection name (format project:region:instance) - you'll need this for CLOUDSQL_INSTANCE_CONNECTION_NAME
gcloud sql instances describe copilot-db --format="value(connectionName)"
```

The Cloud Run backend's service account needs the `roles/cloudsql.client` role
so the Cloud SQL Python Connector (used in `backend/app/db.py`) can authenticate:
```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

## Running the schema

Cloud SQL Studio (GCP Console -> SQL -> your instance -> Studio) gives you a
web SQL editor with no local `psql` setup needed - paste and run:
1. `sql/schema.sql` (creates all tables)
2. `sql/seed_reference_data.sql` (placeholder industry benchmarks + best-practice rules)

Or from Cloud Shell with the Cloud SQL Auth Proxy / `psql` if you prefer a terminal.

## Local setup

1. Copy `.env.example` to `.env` in the repo root and fill in:
   - `CLOUDSQL_INSTANCE_CONNECTION_NAME`, `CLOUDSQL_DB_USER`, `CLOUDSQL_DB_PASSWORD`, `CLOUDSQL_DB_NAME`
   - `META_ACCESS_TOKEN` (confirmed working against `act_906650389058071`, "Toga health"), `META_AD_ACCOUNT_ID`
   - `OPENROUTER_API_KEY` (LLM rationale layer is routed through OpenRouter, model `anthropic/claude-sonnet-5`)
   - `PIPELINE_TRIGGER_SECRET` (any random string — shared secret between Cloud Scheduler and FastAPI)
2. Backend:
   ```
   cd backend
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
3. Frontend:
   ```
   cd frontend
   cp .env.local.example .env.local   # fill in NEXT_PUBLIC_API_URL
   npm install
   npm run dev
   ```

## Scheduling: Cloud Scheduler (replaces pg_cron)

Cloud SQL doesn't support the pg_net/HTTP-callout pattern Supabase offered, so
scheduling moved to GCP-native Cloud Scheduler hitting the FastAPI job
endpoints directly - simpler, and it's the idiomatic GCP way to do this
anyway. Run once, after the backend is deployed:

```bash
BACKEND_URL=$(gcloud run services describe copilot-backend --region us-central1 --format="value(status.url)")

for job in ingest detect recommend; do
  gcloud scheduler jobs create http copilot-$job \
    --schedule="*/15 * * * *" \
    --uri="${BACKEND_URL}/jobs/${job}" \
    --http-method=POST \
    --headers="X-Pipeline-Secret=<PIPELINE_TRIGGER_SECRET>" \
    --location=us-central1
done
```

The three jobs run independently every 15 minutes; `detect` and `recommend`
are idempotent-safe even if they occasionally overlap with a slightly-stale
`ingest` run (see the `upsert`/dedup logic in `backend/app/db.py` and
`backend/app/jobs/*.py`).

## Deploying to GCP (Cloud Run)

Manual first deploy (fastest path to a demo URL):
```bash
gcloud run deploy copilot-backend --source backend --region us-central1 --allow-unauthenticated \
  --set-env-vars CLOUDSQL_INSTANCE_CONNECTION_NAME=...,CLOUDSQL_DB_USER=...,CLOUDSQL_DB_PASSWORD=...,CLOUDSQL_DB_NAME=campaign_copilot,META_ACCESS_TOKEN=...,META_AD_ACCOUNT_ID=...,OPENROUTER_API_KEY=...,PIPELINE_TRIGGER_SECRET=...

gcloud run deploy copilot-frontend --source frontend --region us-central1 --allow-unauthenticated \
  --set-build-env-vars NEXT_PUBLIC_API_URL=<backend-url-from-previous-command>
```

Ongoing deploys via GitHub Actions (`.github/workflows/deploy.yml`) — push to `main`
triggers both. Requires these repo secrets:
- `GCP_PROJECT_ID`, `GCP_SA_KEY` (a service account JSON key with Cloud Run Admin + Cloud SQL Client + Artifact Registry Admin + Service Account User roles)
- `CLOUDSQL_INSTANCE_CONNECTION_NAME`, `CLOUDSQL_DB_USER`, `CLOUDSQL_DB_PASSWORD`, `CLOUDSQL_DB_NAME`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `OPENROUTER_API_KEY`, `PIPELINE_TRIGGER_SECRET`
- `NEXT_PUBLIC_API_URL`

## Known limitations (documented, not silently swallowed)

- Meta `budget_change_log` ingestion is best-effort — Meta's `/activities` edge
  doesn't cleanly expose old/new budget values for every event type. Rows are
  only written when both values are parseable.
- Google Ads connector is a stub per spec Part 16 — wire in once API access is confirmed.
- Ad account has 27 ads, not the 400+ mentioned in the original brief — confirmed
  with the user this is the correct account to build/demo against for now.
- Dashboard live updates are 20-second polling, not true push-based realtime —
  a tradeoff of moving off Supabase Realtime onto Cloud SQL, which has no
  equivalent browser-facing push mechanism without adding Pub/Sub + a WebSocket
  layer (out of scope for the current timeline).
