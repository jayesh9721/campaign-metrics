-- AI Campaign Optimization Copilot - normalized schema
-- Source: PROJECT_BUILD_SPEC.md Part 5, with upsert-safety fixes noted inline.

create table if not exists campaigns (
  campaign_id text primary key,
  campaign_name text not null,
  platform text not null,          -- 'meta' | 'google_ads' | 'linkedin' | 'other'
  brand text,
  account_id text,
  objective text,
  bid_strategy text,
  status text,                     -- 'active' | 'paused' | 'ended'
  start_date date,
  budget_cap numeric,
  budget_type text,                -- 'daily' | 'lifetime'
  created_at timestamptz default now()
);

create table if not exists campaign_daily_metrics (
  id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  date date not null,
  impressions bigint,
  clicks bigint,
  ctr numeric,
  cpc numeric,
  spend numeric,
  conversions numeric,
  conversion_rate numeric,
  revenue numeric,
  roas numeric,
  cpa numeric,
  frequency numeric,
  unique(campaign_id, date)
);
create index if not exists idx_cdm_campaign_date on campaign_daily_metrics(campaign_id, date);

create table if not exists budget_change_log (
  id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  change_date date not null,
  old_budget numeric,
  new_budget numeric,
  changed_by text
);

-- FIX: added unique(campaign_id, segment_id, date) so ingestion can upsert
-- instead of inserting duplicate rows on every poll (spec Part 12 assumes upsert).
create table if not exists audience_segments (
  id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  segment_id text,
  segment_name text,
  date date,
  impressions bigint,
  ctr numeric,
  cpa numeric,
  frequency numeric,
  unique(campaign_id, segment_id, date)
);

-- FIX: added unique(campaign_id, creative_id, date) for the same reason.
create table if not exists creatives (
  id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  creative_id text,
  launch_date date,
  format text,
  date date,
  ctr numeric,
  engagement_rate numeric,
  spend_share numeric,
  unique(campaign_id, creative_id, date)
);

create table if not exists benchmarks (
  id bigint generated always as identity primary key,
  platform text,
  industry text,
  metric_name text,
  benchmark_value numeric
);

create table if not exists best_practices_kb (
  id bigint generated always as identity primary key,
  platform text,
  rule_name text,
  condition text,
  recommended_action text
);

-- FIX: added unique(campaign_id, metric, detected_date) so the anomaly
-- detection job can be re-run safely (idempotent) without duplicating rows.
create table if not exists anomalies (
  anomaly_id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  metric text,
  detected_date date,
  severity text,                    -- 'low' | 'medium' | 'high'
  root_cause_label text,             -- 'audience_fatigue' | 'budget_cap' | 'creative_fatigue' | 'learning_phase' | null
  root_cause_confidence numeric,
  created_at timestamptz default now(),
  unique(campaign_id, metric, detected_date)
);

create table if not exists recommendations (
  rec_id bigint generated always as identity primary key,
  campaign_id text references campaigns(campaign_id),
  anomaly_id bigint references anomalies(anomaly_id),
  type text,                         -- 'budget' | 'bidding' | 'creative'
  rationale text,                    -- filled by Claude, in plain language
  expected_impact_value numeric,
  expected_impact_pct numeric,
  confidence_score numeric,
  priority_score numeric,
  status text default 'pending',     -- 'pending' | 'approved' | 'rejected'
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz default now()
);

-- ADDITION (not in spec Part 5): persistent state for Part 9's human-in-the-loop
-- confidence nudging. Spec says "track approval rate per type, nudge future
-- confidence_score" - this needs somewhere to live across pipeline runs.
create table if not exists recommendation_type_stats (
  type text primary key,             -- 'budget' | 'bidding' | 'creative'
  base_confidence numeric not null,
  approved_count int not null default 0,
  rejected_count int not null default 0,
  updated_at timestamptz default now()
);
insert into recommendation_type_stats (type, base_confidence) values
  ('budget', 0.7), ('bidding', 0.6), ('creative', 0.65)
on conflict (type) do nothing;

create index if not exists idx_anomalies_campaign on anomalies(campaign_id);
create index if not exists idx_recommendations_status_priority on recommendations(status, priority_score desc);
