"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import type { AnomalyWithCampaign, CampaignDailyMetric, Recommendation } from "@/lib/types";
import { formatDate, formatNumber, formatPercent, titleCase } from "@/lib/format";
import { SeverityBadge, StatusBadge, TypeBadge } from "@/components/Badges";
import Sparkline from "@/components/Sparkline";

// Plain-language template per root_cause_label — the LLM already generated
// `rationale` on any linked recommendation; this is a static fallback/summary
// for the root cause itself, which the spec doesn't require an LLM call for.
const ROOT_CAUSE_EXPLANATIONS: Record<string, string> = {
  audience_fatigue:
    "the target audience has likely been shown this campaign too many times — rising frequency is eroding engagement and conversion efficiency.",
  budget_cap:
    "the campaign appears to be constrained by its budget cap, limiting delivery and preventing the platform from spending efficiently through the day.",
  creative_fatigue:
    "the creative assets are wearing out — engagement rates are dropping as the same audience sees the same ad repeatedly.",
  learning_phase:
    "the campaign is still in the platform's learning phase after a recent change, so performance is temporarily volatile while the algorithm recalibrates.",
};

function explainRootCause(anomaly: AnomalyWithCampaign): string {
  if (!anomaly.root_cause_label) {
    return "The detection pipeline has not yet attributed a root cause to this anomaly.";
  }
  const confidencePct = formatPercent((anomaly.root_cause_confidence ?? 0) * 100, 0);
  const detail = ROOT_CAUSE_EXPLANATIONS[anomaly.root_cause_label] ?? "an unspecified underlying issue.";
  return `Our model attributes this ${titleCase(anomaly.severity).toLowerCase()}-severity ${titleCase(
    anomaly.metric,
  )} anomaly to ${titleCase(anomaly.root_cause_label)} with ${confidencePct} confidence — ${detail}`;
}

export default function AnomalyDetailPage() {
  const params = useParams<{ id: string }>();
  const anomalyId = Number(params.id);

  const [anomaly, setAnomaly] = useState<AnomalyWithCampaign | null>(null);
  const [metrics, setMetrics] = useState<CampaignDailyMetric[]>([]);
  const [linkedRecs, setLinkedRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(anomalyId)) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const { data: anomalyRow, error: anomalyErr } = await supabase
        .from("anomalies")
        .select("*, campaigns(campaign_name, platform, brand)")
        .eq("anomaly_id", anomalyId)
        .maybeSingle();
      if (anomalyErr) throw anomalyErr;
      if (!anomalyRow) {
        setNotFound(true);
        setLoading(false);
        return;
      }
      const a = anomalyRow as AnomalyWithCampaign;
      setAnomaly(a);

      const [{ data: metricRows, error: metricErr }, { data: recRows, error: recErr }] = await Promise.all([
        supabase
          .from("campaign_daily_metrics")
          .select("*")
          .eq("campaign_id", a.campaign_id)
          .lte("date", a.detected_date)
          .order("date", { ascending: false })
          .limit(30),
        supabase
          .from("recommendations")
          .select("*")
          .eq("anomaly_id", a.anomaly_id)
          .order("priority_score", { ascending: false }),
      ]);
      if (metricErr) throw metricErr;
      if (recErr) throw recErr;

      setMetrics(((metricRows as CampaignDailyMetric[]) ?? []).slice().reverse());
      setLinkedRecs((recRows as Recommendation[]) ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load anomaly detail.");
    } finally {
      setLoading(false);
    }
  }, [anomalyId]);

  useEffect(() => {
    load();
  }, [load]);

  // Live updates: if the root cause gets attributed, or a linked recommendation
  // is reviewed elsewhere, reflect it here without a refresh (spec Part 13).
  useEffect(() => {
    if (!Number.isFinite(anomalyId)) return;
    const channel = supabase
      .channel(`anomaly-${anomalyId}-live`)
      .on("postgres_changes", { event: "*", schema: "public", table: "anomalies" }, () => load())
      .on("postgres_changes", { event: "*", schema: "public", table: "recommendations" }, () => load())
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [anomalyId, load]);

  const chartData = useMemo(() => {
    if (!anomaly) return [];
    return metrics.map((m) => ({
      date: m.date,
      value: (m as unknown as Record<string, number | null>)[anomaly.metric] ?? null,
    }));
  }, [metrics, anomaly]);

  if (loading) {
    return <div className="text-sm text-slate-500 dark:text-slate-400">Loading anomaly…</div>;
  }

  if (notFound || !anomaly) {
    return (
      <div className="space-y-4">
        <Link href="/anomalies" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
          ← Back to anomalies
        </Link>
        <div className="card p-6 text-sm text-slate-500 dark:text-slate-400">Anomaly not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/anomalies" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
          ← Back to anomalies
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {titleCase(anomaly.metric)} anomaly — {anomaly.campaigns?.campaign_name ?? anomaly.campaign_id}
          </h1>
          <SeverityBadge severity={anomaly.severity} />
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {titleCase(anomaly.campaigns?.platform)} · Detected {formatDate(anomaly.detected_date)}
        </p>
      </div>

      {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}

      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500 dark:text-slate-400">
            {titleCase(anomaly.metric)} — trailing {metrics.length} days
          </h2>
        </div>
        <Sparkline data={chartData} highlightDate={anomaly.detected_date} />
      </div>

      <div className="card p-5">
        <h2 className="text-sm font-medium text-slate-500 dark:text-slate-400">Plain-language explanation</h2>
        <p className="mt-2 text-sm leading-relaxed">{explainRootCause(anomaly)}</p>
      </div>

      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500 dark:text-slate-400">Linked recommendations</h2>
          <Link href="/recommendations" className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400">
            Go to action queue →
          </Link>
        </div>
        {linkedRecs.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No recommendation has been generated for this anomaly yet.</p>
        ) : (
          <ul className="space-y-3">
            {linkedRecs.map((r) => (
              <li key={r.rec_id} className="rounded-lg border border-[var(--border)] p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <TypeBadge type={r.type} />
                  <StatusBadge status={r.status} />
                  <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
                    priority {formatNumber(r.priority_score, 1)}
                  </span>
                </div>
                <p className="text-sm">{r.rationale ?? "No rationale text yet."}</p>
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500 dark:text-slate-400">
                  <span>Expected impact: {formatNumber(r.expected_impact_value, 2)} ({formatPercent(r.expected_impact_pct, 1)})</span>
                  <span>Confidence: {formatPercent((r.confidence_score ?? 0) * 100, 0)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
