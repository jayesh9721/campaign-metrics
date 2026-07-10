// Thin fetch wrapper around the FastAPI backend. Replaces the old direct
// Supabase browser client now that the database lives on GCP Cloud SQL
// (no browser-safe query layer). All reads go through these REST endpoints;
// writes (recommendation review) go through the same backend.

import type {
  AnomalyDetail,
  AnomalyWithCampaign,
  Campaign,
  CampaignDailyMetric,
  DashboardSummary,
  Recommendation,
  RecommendationWithCampaign,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type QueryValue = string | number | boolean | undefined | null;

function buildQuery(params: object = {}): string {
  const entries = (Object.entries(params) as [string, QueryValue][]).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = (body?.detail as string) ?? (body?.message as string) ?? "";
    } catch {
      // Non-JSON error body — fall back to the status text below.
    }
    throw new ApiError(detail || `Request to ${path} failed with status ${res.status}`, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getCampaigns(): Promise<Campaign[]> {
  return apiFetch<Campaign[]>("/campaigns");
}

export function getCampaignDailyMetrics(campaignId: string, days = 30): Promise<CampaignDailyMetric[]> {
  return apiFetch<CampaignDailyMetric[]>(
    `/campaigns/${encodeURIComponent(campaignId)}/daily-metrics${buildQuery({ days })}`,
  );
}

export interface GetAnomaliesParams {
  days?: number;
  severity?: string;
  metric?: string;
  /** Defaults to "open" server-side; pass "all" for every anomaly regardless of status. */
  status?: string;
}

export function getAnomalies(params: GetAnomaliesParams = {}): Promise<AnomalyWithCampaign[]> {
  return apiFetch<AnomalyWithCampaign[]>(`/anomalies${buildQuery(params)}`);
}

export function getAnomaly(anomalyId: number): Promise<AnomalyDetail> {
  return apiFetch<AnomalyDetail>(`/anomalies/${anomalyId}`);
}

export interface GetRecommendationsParams {
  status?: string;
  type?: string;
}

export function getRecommendations(params: GetRecommendationsParams = {}): Promise<RecommendationWithCampaign[]> {
  return apiFetch<RecommendationWithCampaign[]>(`/recommendations${buildQuery(params)}`);
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>("/dashboard-summary");
}

export function reviewRecommendation(
  recId: number,
  status: "approved" | "rejected",
  reviewedBy: string,
): Promise<Recommendation> {
  return apiFetch<Recommendation>(`/recommendations/${recId}/review`, {
    method: "POST",
    body: JSON.stringify({ status, reviewed_by: reviewedBy }),
  });
}
