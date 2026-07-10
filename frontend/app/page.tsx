"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getDashboardSummary } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";
import { formatDate, formatNumber, formatPercent, titleCase } from "@/lib/format";
import { SeverityBadge } from "@/components/Badges";

const POLL_INTERVAL_MS = 20_000;

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await getDashboardSummary();
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // No more Supabase Realtime — the DB now lives on Cloud SQL with no
  // browser-safe realtime mechanism, so we poll the backend instead.
  useEffect(() => {
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

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

  if (!summary) {
    return <div className="text-sm text-slate-500 dark:text-slate-400">No dashboard data available.</div>;
  }

  const topRoas = summary.top_roas_campaign;
  const mostUrgent = summary.most_urgent_anomaly;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Live portfolio overview across all connected campaigns.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Portfolio health score"
          value={`${summary.health_score}`}
          sub="100 minus severity-weighted open anomalies"
        />
        <StatCard
          label="Active alerts (7d)"
          value={`${summary.active_alert_count}`}
          sub="Anomalies detected in the last 7 days"
        />
        <StatCard
          label="Pending actions"
          value={`${summary.pending_action_count}`}
          sub="Recommendations awaiting review"
        />
        <StatCard
          label="Approval rate"
          value={summary.approval_rate_pct === null ? "—" : formatPercent(summary.approval_rate_pct, 0)}
          sub="Approved ÷ (approved + rejected)"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Time saved this week</div>
          <div className="mt-2 text-3xl font-semibold">
            ≈{summary.time_saved_hours.toLocaleString(undefined, { maximumFractionDigits: 1 })} hrs
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Estimated at 15 min of manual analyst review avoided per anomaly detected in the last 7 days.
          </p>
        </div>

        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Top ROAS campaign</div>
          {topRoas ? (
            <>
              <div className="mt-2 text-xl font-semibold">{topRoas.campaign_name ?? topRoas.campaign_id}</div>
              <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                ROAS {formatNumber(topRoas.roas, 2)}x
              </div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">as of {formatDate(topRoas.date)}</div>
            </>
          ) : (
            <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">No metrics available yet.</div>
          )}
        </div>

        <div className="card p-5">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">Most urgent anomaly</div>
          {mostUrgent ? (
            <>
              <div className="mt-2 flex items-center gap-2">
                <SeverityBadge severity={mostUrgent.severity} />
                <span className="text-sm font-medium">{titleCase(mostUrgent.metric)}</span>
              </div>
              <div className="mt-1 text-sm">{mostUrgent.campaign_name ?? mostUrgent.campaign_id}</div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                Detected {formatDate(mostUrgent.detected_date)}
              </div>
              {mostUrgent.top_recommendation ? (
                <p className="mt-3 line-clamp-3 text-xs text-slate-500 dark:text-slate-400">
                  {mostUrgent.top_recommendation.rationale ?? "No rationale text yet."}
                </p>
              ) : (
                <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">No recommendation generated yet.</p>
              )}
              <Link
                href={`/anomalies/${mostUrgent.anomaly_id}`}
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
