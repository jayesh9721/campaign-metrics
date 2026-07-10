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
2. Deploy the Edge Function: `supabase functions deploy trigger-pipeline` (set `BACKEND_URL` to your Render backend URL and `PIPELINE_TRIGGER_SECRET` as function secrets via `supabase secrets set`).
3. Run `sql/schedule_cron.sql` in the SQL editor, filling in your project ref and anon key.

## Deploying: Render (backend) + Vercel (frontend)

No GCP, no billing card, no CLI auth dance — both platforms deploy straight
from the GitHub repo and auto-redeploy on every push to `main`.

### Backend on Render

1. Sign in to [render.com](https://render.com) with GitHub.
2. **New +** → **Blueprint** → select the `Campaign-Whisperer` repo. Render
   reads `render.yaml` at the repo root automatically and proposes the
   `campaign-copilot-backend` web service (Python, free plan, root dir
   `backend`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
3. It'll prompt for the env vars marked `sync: false` in `render.yaml` — fill in:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `META_ACCESS_TOKEN`,
   `META_AD_ACCOUNT_ID`, `OPENROUTER_API_KEY`, `PIPELINE_TRIGGER_SECRET`
   (same values as your local `.env`).
4. Deploy. Copy the resulting URL (`https://campaign-copilot-backend-xxxx.onrender.com`).
5. Confirm it's alive: `curl https://<your-render-url>/health` → `{"status":"ok"}`.

Free-tier note: the service sleeps after 15 minutes idle and takes ~30-50s to
wake on the next request. Since the automation cron also fires every 15
minutes, expect the first hit after a quiet period to be slow but not fail —
upgrade to a paid instance if that latency becomes a problem for the demo.

### Frontend on Vercel

1. Sign in to [vercel.com](https://vercel.com) with GitHub.
2. **Add New** → **Project** → import `Campaign-Whisperer`.
3. In the import screen, set **Root Directory** to `frontend` (Vercel
   auto-detects Next.js once you do).
4. Add env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   (same as `frontend/.env.local`), and `NEXT_PUBLIC_API_URL` = the Render
   backend URL from step above.
5. Deploy. Vercel gives you a `https://campaign-whisperer.vercel.app`-style URL.

## Known limitations (documented, not silently swallowed)

- Meta `budget_change_log` ingestion is best-effort — Meta's `/activities` edge
  doesn't cleanly expose old/new budget values for every event type. Rows are
  only written when both values are parseable.
- Google Ads connector is a stub per spec Part 16 — wire in once API access is confirmed.
- Ad account has 27 ads, not the 400+ mentioned in the original brief — confirmed
  with the user this is the correct account to build/demo against for now.
