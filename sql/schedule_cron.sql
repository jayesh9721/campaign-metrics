-- Run once in the Supabase SQL editor after deploying the trigger-pipeline
-- Edge Function. Requires the pg_cron and pg_net extensions (enable both
-- under Database > Extensions in the Supabase dashboard first).

select cron.schedule(
  'campaign-copilot-pipeline',
  '*/15 * * * *',  -- every 15 minutes, per spec Part 12
  $$
  select net.http_post(
    url := 'https://<project-ref>.supabase.co/functions/v1/trigger-pipeline',
    headers := jsonb_build_object(
      'Authorization', 'Bearer <SUPABASE_ANON_KEY>',
      'Content-Type', 'application/json'
    )
  );
  $$
);

-- To inspect scheduled jobs:  select * from cron.job;
-- To unschedule:              select cron.unschedule('campaign-copilot-pipeline');
