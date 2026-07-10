"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import type { AnomalyWithCampaign, RecommendationWithCampaign } from "@/lib/types";
import { daysAgo, formatDate, formatNumber, formatPercent, severityRank, titleCase } from "@/lib/format";
import { SeverityBadge } from "@/components/Badges";

interface TopRoasRow {
  campaign_id: string;
  date: string;
  roas: number | null;
  campaigns: { campaign_name: string; platform: string } | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface SyncResult {
  ingest?: Record<string, { campaigns: number; daily_metrics: number; budget_changes: number; audience_rows: number; creative_rows: number }>;
  detect?: { anomalies_detected: number };
  recommend?: { anomalies_processed: number; recommendations_created: number };
}

export default function DashboardPage() {
  const [anomalies, setAnomalies] = useState<AnomalyWithCampaign[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationWithCampaign[]>([]);
  const [topRoas, setTopRoas] = useState<TopRoasRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [syncing, setSyncing] = useState(false);
  const [syncStep, setSyncStep] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const loadAnomaliesAndRecs = useCallback(async () => {
    const [{ data: anomalyData, error: anomalyErr }, { data: recData, error: recErr }] = await Promise.all([
      supabase
        .from("anomalies")
        .select("*, campaigns(campaign_name, platform, brand)")
        .order("detected_date", { ascending: false }),
      supabase
        .from("recommendations")
        .select("*, campaigns(campaign_name, platform, brand)")
        .order("priority_score", { ascending: false }),
    ]);
    if (anomalyErr) throw anomalyErr;
    if (recErr) throw recErr;
    setAnomalies((anomalyData as AnomalyWithCampaign[]) ?? []);
    setRecommendations((recData as RecommendationWithCampaign[]) ?? []);
  }, []);

  const loadTopRoas = useCallback(async () => {
    const { data: latestDateRows, error: dateErr } = await supabase
      .from("campaign_daily_metrics")
      .select("date")
      .order("date", { ascending: false })
      .limit(1);
    if (dateErr) throw dateErr;
    const latestDate = latestDateRows?.[0]?.date as string | undefined;
    if (!latestDate) {
      setTopRoas(null);
      return;
    }
    const { data, error: roasErr } = await supabase
      .from("campaign_daily_metrics")
      .select("campaign_id, date, roas, campaigns(campaign_name, platform)")
      .eq("date", latestDate)
      .order("roas", { ascending: false })
      .limit(1);
    if (roasErr) throw roasErr;
    setTopRoas((data?.[0] as unknown as TopRoasRow) ?? null);
  }, []);

  const loadAll = useCallback(async () => {
    try {
      setError(null);
      await Promise.all([loadAnomaliesAndRecs(), loadTopRoas()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, [loadAnomaliesAndRecs, loadTopRoas]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const runSync = useCallback(async () => {
    if (!API_URL) {
      setSyncError("NEXT_PUBLIC_API_URL is not configured.");
      return;
    }
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    const result: SyncResult = {};
    try {
      setSyncStep("Pulling latest campaign data…");
      const ingestRes = await fetch(`${API_URL}/jobs/ingest`, { method: "POST" });
      if (!ingestRes.ok) throw new Error(`Ingest failed (${ingestRes.status})`);
      result.ingest = await ingestRes.json();
      setSyncResult({ ...result });

      setSyncStep("Scanning for anomalies…");
      const detectRes = await fetch(`${API_URL}/jobs/detect`, { method: "POST" });
      if (!detectRes.ok) throw new Error(`Anomaly detection failed (${detectRes.status})`);
      result.detect = await detectRes.json();
      setSyncResult({ ...result });

      setSyncStep("Diagnosing root causes and writing recommendations…");
      const recommendRes = await fetch(`${API_URL}/jobs/recommend`, { method: "POST" });
      if (!recommendRes.ok) throw new Error(`Recommendation generation failed (${recommendRes.status})`);
      result.recommend = await recommendRes.json();
      setSyncResult({ ...result });

      setSyncStep(null);
      await loadAll();
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Sync failed.");
      setSyncStep(null);
    } finally {
      setSyncing(false);
    }
  }, [loadAll]);

  // Live updates: refetch whenever anomalies/recommendations change server-side
  // (new anomaly detected, recommendation approved/rejected, etc.) — spec Part 13.
  useEffect(() => {
    const channel = supabase
      .channel("dashboard-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "anomalies" }, () => {
        loadAnomaliesAndRecs();
      })
      .on("postgres_changes", { event: "*", schema: "public", table: "recommendations" }, () => {
        loadAnomaliesAndRecs();
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [loadAnomaliesAndRecs]);

  const stats = useMemo(() => {
    const isOpen = (anomalyId: number) => {
      const linked = recommendations.filter((r) => r.anomaly_id === anomalyId);
      // ASSUMPTION: an anomaly is "open" until at least one linked recommendation
      // has been reviewed (approved or rejected). No linked recs yet = still open.
      return !linked.some((r) => r.status === "approved" || r.status === "rejected");
    };

    const openHighSeverity = anomalies.filter((a) => isOpen(a.anomaly_id) && a.severity === "high").length;
    const openMediumSeverity = anomalies.filter((a) => isOpen(a.anomaly_id) && a.severity === "medium").length;

    // ASSUMPTION (documented): portfolio health score formula, not specified by the
    // spec. 100 - (open_high_severity_anomalies * 10) - (open_medium_severity_anomalies * 4), clamped to [0, 100].
    const healthScore = Math.max(0, Math.min(100, 100 - openHighSeverity * 10 - openMediumSeverity * 4));

    const activeAlerts = anomalies.filter((a) => daysAgo(a.detected_date) <= 7).length;
    const pendingActions = recommendations.filter((r) => r.status === "pending").length;

    // ASSUMPTION (documented): "time saved" = anomalies_detected_last_7_days * 15 minutes,
    // as a stand-in analyst-review-time-avoided metric (spec Part 14).
    const timeSavedHours = (activeAlerts * 15) / 60;

    const reviewed = recommendations.filter((r) => r.status === "approved" || r.status === "rejected");
    const approved = reviewed.filter((r) => r.status === "approved").length;
    const approvalRate = reviewed.length > 0 ? (approved / reviewed.length) * 100 : null;

    const mostUrgent = [...anomalies].sort((a, b) => {
      const sevDiff = severityRank(b.severity) - severityRank(a.severity);
      if (sevDiff !== 0) return sevDiff;
      return new Date(b.detected_date).getTime() - new Date(a.detected_date).getTime();
    })[0];

    const topRecForUrgent = mostUrgent
      ? [...recommendations]
          .filter((r) => r.anomaly_id === mostUrgent.anomaly_id)
          .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))[0]
      : undefined;

    return {
      healthScore,
      activeAlerts,
      pendingActions,
      timeSavedHours,
      approvalRate,
      mostUrgent,
      topRecForUrgent,
    };
  }, [anomalies, recommendations]);

  if (loading) {
    return <div className="text-sm text-slate-500 dark:text-slate-400">Loading dashboard…</div>;
  }

  if (error) {
    return (
      <div className="card p-4 text-sm text-red-600 dark:text-red-400">
        Failed to load dashboard: {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Live portfolio overview across all connected campaigns.
          </p>
        </div>
        <button
          onClick={runSync}
          disabled={syncing}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {syncing ? (syncStep ?? "Syncing…") : "Sync Now"}
        </button>
      </div>

      {syncError && (
        <div className="card p-4 text-sm text-red-600 dark:text-red-400">Sync failed: {syncError}</div>
      )}

      {syncResult && !syncing && (
        <div className="card p-4 text-sm">
          <div className="font-medium">Sync complete — real data pulled and processed:</div>
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {syncResult.ingest && (
              <div>
                <div className="text-xs uppercase text-slate-400 dark:text-slate-500">Ingested</div>
                {Object.entries(syncResult.ingest).map(([source, counts]) => (
                  <div key={source} className="text-xs text-slate-500 dark:text-slate-400">
                    {source}: {counts.campaigns} campaigns, {counts.daily_metrics} metric rows
                  </div>
                ))}
              </div>
            )}
            {syncResult.detect && (
              <div>
                <div className="text-xs uppercase text-slate-400 dark:text-slate-500">Detected</div>
                <div className="text-lg font-semibold">{syncResult.detect.anomalies_detected}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">new anomalies</div>
              </div>
            )}
            {syncResult.recommend && (
              <div>
                <div className="text-xs uppercase text-slate-400 dark:text-slate-500">Recommended</div>
                <div className="text-lg font-semibold">{syncResult.recommend.recommendations_created}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  from {syncResult.recommend.anomalies_processed} anomalies processed
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Portfolio health score"
          value={`${stats.healthScore}`}
          sub="100 minus severity-weighted open anomalies"
        />
        <StatCard label="Active alerts (7d)" value={`${stats.activeAlerts}`} sub="Anomalies detected in the last 7 days" />
        <StatCard label="Pending actions" value={`${stats.pendingActions}`} sub="Recommendations awaiting review" />
        <StatCard
          label="Approval rate"
          value={stats.approvalRate === null ? "—" : formatPercent(stats.approvalRate, 0)}
          sub="Approved ÷ (approved + rejected)"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Time saved this week</div>
          <div className="mt-2 text-3xl font-semibold">
            ≈{stats.timeSavedHours.toLocaleString(undefined, { maximumFractionDigits: 1 })} hrs
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Estimated at 15 min of manual analyst review avoided per anomaly detected in the last 7 days.
          </p>
        </div>

        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Top ROAS campaign</div>
          {topRoas ? (
            <>
              <div className="mt-2 text-xl font-semibold">{topRoas.campaigns?.campaign_name ?? topRoas.campaign_id}</div>
              <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {titleCase(topRoas.campaigns?.platform)} · ROAS {formatNumber(topRoas.roas, 2)}x
              </div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">as of {formatDate(topRoas.date)}</div>
            </>
          ) : (
            <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">No metrics available yet.</div>
          )}
        </div>

        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Most urgent anomaly</div>
          {stats.mostUrgent ? (
            <>
              <div className="mt-2 flex items-center gap-2">
                <SeverityBadge severity={stats.mostUrgent.severity} />
                <span className="text-sm font-medium">{titleCase(stats.mostUrgent.metric)}</span>
              </div>
              <div className="mt-1 text-sm">
                {stats.mostUrgent.campaigns?.campaign_name ?? stats.mostUrgent.campaign_id}
              </div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                Detected {formatDate(stats.mostUrgent.detected_date)}
              </div>
              {stats.topRecForUrgent ? (
                <p className="mt-3 line-clamp-3 text-xs text-slate-500 dark:text-slate-400">
                  {stats.topRecForUrgent.rationale ?? "No rationale text yet."}
                </p>
              ) : (
                <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">No recommendation generated yet.</p>
              )}
              <Link
                href={`/anomalies/${stats.mostUrgent.anomaly_id}`}
                className="mt-3 inline-block text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                View root cause →
              </Link>
            </>
          ) : (
            <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">No anomalies detected yet.</div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link
          href="/anomalies"
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          View all anomalies
        </Link>
        <Link
          href="/recommendations"
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          Open action queue
        </Link>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card p-5">
      <div className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-2 text-3xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">{sub}</div>
    </div>
  );
}
