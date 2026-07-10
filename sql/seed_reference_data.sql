-- Placeholder industry benchmarks and best-practice rules for the demo.
-- These are plausible published-average figures for health/wellness paid
-- social (matches the "Toga health" account), NOT pulled from a licensed
-- benchmark provider. Replace with real numbers if/when available -
-- see PROJECT_BUILD_SPEC.md Part 5's benchmarks table.

insert into benchmarks (platform, industry, metric_name, benchmark_value) values
  ('meta', 'health_wellness', 'ctr', 1.2),
  ('meta', 'health_wellness', 'cpc', 0.9),
  ('meta', 'health_wellness', 'cpa', 22.0),
  ('meta', 'health_wellness', 'roas', 2.5),
  ('meta', 'health_wellness', 'frequency', 2.8);

insert into best_practices_kb (platform, rule_name, condition, recommended_action) values
  ('meta', 'budget_cap_reallocation', 'spend/budget_cap > 0.95 and impressions declining 3d', 'Increase daily budget or reallocate from a lower-ROAS campaign in the same brand'),
  ('meta', 'learning_phase_suppression', 'days_since_bid_strategy_change <= 7 and cpa volatile', 'Do not act - campaign is still in Meta''s learning phase, let it stabilize'),
  ('meta', 'creative_fatigue_refresh', 'ctr declining 3+ consecutive checks, frequency stable', 'Refresh ad creative - swap primary image/video and copy'),
  ('meta', 'audience_fatigue_expand', 'ctr declining while frequency rising on same segment', 'Expand or rotate audience targeting to reduce overexposure'),
  ('meta', 'bidding_strategy_shift', 'cpa rising 7d trend, budget not capped, bid strategy stable > 7d', 'Switch to Cost Cap or Target ROAS bidding to regain efficiency')
on conflict do nothing;
