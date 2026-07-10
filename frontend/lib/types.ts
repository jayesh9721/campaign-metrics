// Mirrors sql/schema.sql. Kept intentionally loose (nullable) since the
// pipeline can leave fields unset (e.g. root_cause_label before the LLM runs).

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
  created_at: string | null;
}

export interface CampaignDailyMetric {
  id: number;
  campaign_id: string;
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
  created_at: string | null;
}

export interface AnomalyWithCampaign extends Anomaly {
  campaigns: Pick<Campaign, "campaign_name" | "platform" | "brand"> | null;
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
  created_at: string | null;
}

export interface RecommendationWithCampaign extends Recommendation {
  campaigns: Pick<Campaign, "campaign_name" | "platform" | "brand"> | null;
}
