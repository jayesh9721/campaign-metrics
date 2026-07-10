// Thin cron-to-HTTP bridge. All real logic (ingestion, anomaly detection,
// root cause, recommendations) lives in the Python FastAPI backend per
// PROJECT_BUILD_SPEC.md Part 3 - this function's only job is to be the thing
// pg_cron can call natively, which then calls the backend's job endpoints.
//
// Deploy: supabase functions deploy trigger-pipeline
// Schedule via pg_cron: see sql/schedule_cron.sql

const BACKEND_URL = Deno.env.get("BACKEND_URL")!; // e.g. https://copilot-backend-xxxx.run.app
const PIPELINE_TRIGGER_SECRET = Deno.env.get("PIPELINE_TRIGGER_SECRET")!;

const STEPS = ["/jobs/ingest", "/jobs/detect", "/jobs/recommend"];

Deno.serve(async (_req) => {
  const results: Record<string, unknown> = {};

  for (const step of STEPS) {
    try {
      const res = await fetch(`${BACKEND_URL}${step}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Pipeline-Secret": PIPELINE_TRIGGER_SECRET,
        },
      });
      results[step] = { status: res.status, body: await res.text() };
      if (!res.ok) break; // don't run detect/recommend on a failed ingest
    } catch (err) {
      results[step] = { error: String(err) };
      break;
    }
  }

  return new Response(JSON.stringify(results), {
    headers: { "Content-Type": "application/json" },
  });
});
