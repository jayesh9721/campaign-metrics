"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getRecommendations, reviewRecommendation } from "@/lib/api";
import type { RecommendationWithCampaign } from "@/lib/types";
import { formatDateTime, formatNumber, formatPercent, titleCase } from "@/lib/format";
import { StatusBadge, TypeBadge } from "@/components/Badges";

const POLL_INTERVAL_MS = 20_000;

export default function RecommendationsPage() {
  const [recommendations, setRecommendations] = useState<RecommendationWithCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actioningIds, setActioningIds] = useState<Record<number, boolean>>({});

  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await getRecommendations();
      setRecommendations(data ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // No more Supabase Realtime — poll the backend instead. This also
  // reconciles the optimistic status update below shortly after it lands.
  useEffect(() => {
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const filtered = useMemo(() => {
    let rows = recommendations;
    if (statusFilter !== "all") rows = rows.filter((r) => r.status === statusFilter);
    if (typeFilter !== "all") rows = rows.filter((r) => r.type === typeFilter);
    return rows;
  }, [recommendations, statusFilter, typeFilter]);

  const handleReview = useCallback(
    async (rec: RecommendationWithCampaign, status: "approved" | "rejected") => {
      const previous = rec.status;
      setActionError(null);
      // Optimistic update.
      setRecommendations((prev) => prev.map((r) => (r.rec_id === rec.rec_id ? { ...r, status } : r)));
      setActioningIds((prev) => ({ ...prev, [rec.rec_id]: true }));
      try {
        await reviewRecommendation(rec.rec_id, status, "demo-user");
        // Reconcile with server truth (also picked up automatically via polling).
        await load();
      } catch (e) {
        setRecommendations((prev) => prev.map((r) => (r.rec_id === rec.rec_id ? { ...r, status: previous } : r)));
        setActionError(
          `Failed to ${status === "approved" ? "approve" : "reject"} recommendation #${rec.rec_id}: ${
            e instanceof Error ? e.message : "unknown error"
          }`,
        );
      } finally {
        setActioningIds((prev) => {
          const next = { ...prev };
          delete next[rec.rec_id];
          return next;
        });
      }
    },
    [load],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Recommendations</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          AI-generated optimization actions, ordered by priority. Approve or reject to close the loop.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Filter
          label="Status"
          value={statusFilter}
          onChange={setStatusFilter}
          options={["all", "pending", "approved", "rejected"]}
        />
        <Filter label="Type" value={typeFilter} onChange={setTypeFilter} options={["all", "budget", "bidding", "creative"]} />
        <div className="ml-auto text-xs text-slate-400 dark:text-slate-500">
          {filtered.length} of {recommendations.length} recommendations
        </div>
      </div>

      {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}
      {actionError && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{actionError}</div>}

      {loading ? (
        <div className="text-sm text-slate-500 dark:text-slate-400">Loading recommendations…</div>
      ) : filtered.length === 0 ? (
        <div className="card p-6 text-sm text-slate-500 dark:text-slate-400">No recommendations match these filters.</div>
      ) : (
        <div className="space-y-4">
          {filtered.map((r) => {
            const busy = !!actioningIds[r.rec_id];
            return (
              <div key={r.rec_id} className="card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{r.campaign_name ?? r.campaign_id}</span>
                      <TypeBadge type={r.type} />
                      <StatusBadge status={r.status} />
                    </div>
                    <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                      {titleCase(r.platform)} · priority {formatNumber(r.priority_score, 1)}
                      {r.anomaly_id ? (
                        <>
                          {" · "}
                          <Link href={`/anomalies/${r.anomaly_id}`} className="text-blue-600 hover:underline dark:text-blue-400">
                            related anomaly →
                          </Link>
                        </>
                      ) : null}
                    </div>
                  </div>
                  {r.status === "pending" ? (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleReview(r, "approved")}
                        disabled={busy}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleReview(r, "rejected")}
                        disabled={busy}
                        className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-400 dark:text-slate-500">
                      Reviewed {formatDateTime(r.reviewed_at)}
                      {r.reviewed_by ? ` by ${r.reviewed_by}` : ""}
                    </div>
                  )}
                </div>

                <p className="mt-3 text-sm leading-relaxed">{r.rationale ?? "No rationale text yet."}</p>

                <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500 dark:text-slate-400">
                  <span>
                    Expected impact: {formatNumber(r.expected_impact_value, 2)} ({formatPercent(r.expected_impact_pct, 1)})
                  </span>
                  <span>Confidence: {formatPercent((r.confidence_score ?? 0) * 100, 0)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Filter({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <select
        className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === "all" ? "All" : titleCase(o)}
          </option>
        ))}
      </select>
    </label>
  );
}
