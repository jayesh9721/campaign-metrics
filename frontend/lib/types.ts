// Mirrors sql/schema.sql, as served by the FastAPI backend (Cloud SQL/Postgres
// behind the scenes). Kept intentionally loose (nullable) since the pipeline
// can leave fields unset (e.g. root_cause_label before the LLM runs).

export type Platform = "meta" | "google_ads" | "linkedin" | "other" | string;
export type CampaignStatus = "active" | "paused" | "ended" | string;
export type Severity = "low" | "medium" | "high" | string;
export type RootCauseLabel =
  | "audience_fatigue"
  | "budget_cap"
  | "creative_fatigue"
  | "learning_phase"
  | null;
export type RecommendationType = "budget" | "bidding" | "creative" | string;
export type RecommendationStatus = "pending" | "approved" | "rejected" | string;

export interface Campaign {
  campaign_id: string;
  campaign_name: string;
  platform: Platform;
  brand: string | null;
  account_id: string | null;
  objective: string | null;
  bid_strategy: string | null;
  status: CampaignStatus | null;
  start_date: string | null;
  budget_cap: number | null;
  budget_type: string | null;
}

export interface CampaignDailyMetric {
  id?: number;
  campaign_id?: string;
  date: string;
  impressions: number | null;
  clicks: number | null;
  ctr: number | null;
  cpc: number | null;
  spend: number | null;
  conversions: number | null;
  conversion_rate: number | null;
  revenue: number | null;
  roas: number | null;
  cpa: number | null;
  frequency: number | null;
}

export interface Anomaly {
  anomaly_id: number;
  campaign_id: string;
  metric: string;
  detected_date: string;
  severity: Severity;
  root_cause_label: RootCauseLabel;
  root_cause_confidence: number | null;
  created_at?: string | null;
}

// The backend joins campaign_name / platform / brand directly onto the
// anomaly row (flattened), rather than nesting a `campaigns` object — see
// GET /anomalies and GET /anomalies/{id} in the API contract.
export interface AnomalyWithCampaign extends Anomaly {
  campaign_name: string | null;
  platform: Platform | null;
  brand: string | null;
}

export interface Recommendation {
  rec_id: number;
  campaign_id: string;
  anomaly_id: number | null;
  type: RecommendationType;
  rationale: string | null;
  expected_impact_value: number | null;
  expected_impact_pct: number | null;
  confidence_score: number | null;
  priority_score: number | null;
  status: RecommendationStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at?: string | null;
}

// Same flattening convention as AnomalyWithCampaign — see GET /recommendations.
export interface RecommendationWithCampaign extends Recommendation {
  campaign_name: string | null;
  platform: Platform | null;
  brand: string | null;
}

// GET /anomalies/{anomaly_id} — the anomaly (with joined campaign info) plus
// its trailing daily metrics (for the sparkline) and any linked recommendations.
export interface AnomalyDetail extends AnomalyWithCampaign {
  daily_metrics: CampaignDailyMetric[];
  recommendations: Recommendation[];
}

export interface TopRoasCampaign {
  campaign_id: string;
  campaign_name: string;
  roas: number | null;
  date: string;
}

export interface TopRecommendationSummary {
  rec_id: number;
  rationale: string | null;
  priority_score: number | null;
}

// GET /dashboard-summary
export interface DashboardSummary {
  health_score: number;
  active_alert_count: number;
  pending_action_count: number;
  top_roas_campaign: TopRoasCampaign | null;
  most_urgent_anomaly: (AnomalyWithCampaign & { top_recommendation: TopRecommendationSummary | null }) | null;
  time_saved_hours: number;
  approval_rate_pct: number | null;
}
