# AI Campaign Optimization Copilot

Built against `PROJECT_BUILD_SPEC.md`. See that file for the full spec this implements.

## Architecture

```
connectors (Meta real / LinkedIn+other mocked / Google Ads stub)
        |
        v
  normalized schema (Supabase Postgres, sql/schema.sql)
        |
        v
anomaly detection -> root cause engine -> recommendation engine -> Claude rationale
        |
        v
FastAPI job endpoints (backend/app/jobs/*)  <-- triggered every 15 min by
        |                                       Supabase pg_cron -> Edge Function
        v
Next.js frontend (Supabase Realtime subscriptions on anomalies/recommendations)
```

Everything above the connector layer reads/writes only the normalized schema — no module calls a platform API directly (spec Part 3).

## Local setup

1. Copy `.env.example` to `.env` in the repo root and fill in:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (Supabase dashboard -> Settings -> API)
   - `META_ACCESS_TOKEN` (already confirmed working against `act_906650389058071`, "Toga health")
   - `OPENROUTER_API_KEY` (LLM rationale layer is routed through OpenRouter, model `anthropic/claude-sonnet-5`, rather than calling Anthropic directly)
   - `PIPELINE_TRIGGER_SECRET` (any random string — shared secret between the Edge Function and FastAPI)
2. Run `sql/schema.sql` in the Supabase SQL editor (creates all tables).
3. Backend:
   ```
   cd backend
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
4. Frontend:
   ```
   cd frontend
   cp .env.local.example .env.local   # fill in NEXT_PUBLIC_* vars
   npm install
   npm run dev
   ```

## Scheduling

Chosen: **pg_cron + Supabase Edge Function**, per spec Part 12. The Edge Function
(`supabase/functions/trigger-pipeline`) is a thin bridge — it does not contain
business logic, it just calls the FastAPI backend's `/jobs/ingest`, `/jobs/detect`,
`/jobs/recommend` endpoints in sequence. This keeps all real logic in Python
(matches the fixed tech stack) while still using Supabase-native scheduling.

Setup:
1. Enable the `pg_cron` and `pg_net` extensions in the Supabase dashboard (Database -> Extensions).
2. Deploy the Edge Function: `supabase functions deploy trigger-pipeline` (set `BACKEND_URL` and `PIPELINE_TRIGGER_SECRET` as function secrets via `supabase secrets set`).
3. Run `sql/schedule_cron.sql` in the SQL editor, filling in your project ref and anon key.

## Deploying to GCP (Cloud Run)

One-time setup (run these yourself — `gcloud auth login` needs an interactive
browser, which this build environment can't do):

```
gcloud auth login
gcloud projects create <PROJECT_ID>          # or use an existing project
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

Manual first deploy (fastest path to a demo URL today):
```
gcloud run deploy copilot-backend --source backend --region us-central1 --allow-unauthenticated
gcloud run deploy copilot-frontend --source frontend --region us-central1 --allow-unauthenticated \
  --set-build-env-vars NEXT_PUBLIC_SUPABASE_URL=...,NEXT_PUBLIC_SUPABASE_ANON_KEY=...,NEXT_PUBLIC_API_URL=<backend-url-from-previous-command>
```

Ongoing deploys via GitHub Actions (`.github/workflows/deploy.yml`) — push to `main`
triggers both. Requires these repo secrets:
- `GCP_PROJECT_ID`, `GCP_SA_KEY` (a service account JSON key with Cloud Run Admin + Artifact Registry Admin + Service Account User roles)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `OPENROUTER_API_KEY`, `PIPELINE_TRIGGER_SECRET`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`

## Known limitations (documented, not silently swallowed)

- Meta `budget_change_log` ingestion is best-effort — Meta's `/activities` edge
  doesn't cleanly expose old/new budget values for every event type. Rows are
  only written when both values are parseable.
- Google Ads connector is a stub per spec Part 16 — wire in once API access is confirmed.
- Ad account has 27 ads, not the 400+ mentioned in the original brief — confirmed
  with the user this is the correct account to build/demo against for now.
