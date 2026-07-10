"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import type { AnomalyWithCampaign } from "@/lib/types";
import { formatDate, formatPercent, severityRank, titleCase } from "@/lib/format";
import { SeverityBadge } from "@/components/Badges";

type SortKey = "detected_date" | "severity" | "metric" | "campaign";
type SortDir = "asc" | "desc";

export default function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<AnomalyWithCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [metricFilter, setMetricFilter] = useState<string>("all");
  const [campaignFilter, setCampaignFilter] = useState<string>("all");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("detected_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const load = useCallback(async () => {
    try {
      setError(null);
      const { data, error: err } = await supabase
        .from("anomalies")
        .select("*, campaigns(campaign_name, platform, brand)")
        .order("detected_date", { ascending: false });
      if (err) throw err;
      setAnomalies((data as AnomalyWithCampaign[]) ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load anomalies.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Live updates per spec Part 13 — no polling.
  useEffect(() => {
    const channel = supabase
      .channel("anomalies-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "anomalies" }, () => {
        load();
      })
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [load]);

  const metrics = useMemo(
    () => Array.from(new Set(anomalies.map((a) => a.metric).filter(Boolean))).sort(),
    [anomalies],
  );

  const campaignOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const a of anomalies) {
      if (!seen.has(a.campaign_id)) seen.set(a.campaign_id, a.campaigns?.campaign_name ?? a.campaign_id);
    }
    return Array.from(seen.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [anomalies]);

  const filtered = useMemo(() => {
    let rows = anomalies;
    if (severityFilter !== "all") rows = rows.filter((a) => a.severity === severityFilter);
    if (metricFilter !== "all") rows = rows.filter((a) => a.metric === metricFilter);
    if (campaignFilter !== "all") rows = rows.filter((a) => a.campaign_id === campaignFilter);
    if (dateFrom) rows = rows.filter((a) => a.detected_date >= dateFrom);
    if (dateTo) rows = rows.filter((a) => a.detected_date <= dateTo);

    const dir = sortDir === "asc" ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      switch (sortKey) {
        case "severity":
          return (severityRank(a.severity) - severityRank(b.severity)) * dir;
        case "metric":
          return a.metric.localeCompare(b.metric) * dir;
        case "campaign":
          return (a.campaigns?.campaign_name ?? a.campaign_id).localeCompare(
            b.campaigns?.campaign_name ?? b.campaign_id,
          ) * dir;
        default:
          return (new Date(a.detected_date).getTime() - new Date(b.detected_date).getTime()) * dir;
      }
    });
    return rows;
  }, [anomalies, severityFilter, metricFilter, campaignFilter, dateFrom, dateTo, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sortIndicator = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Anomalies</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          All detected performance anomalies across your campaigns.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Filter label="Severity" value={severityFilter} onChange={setSeverityFilter} options={["all", "high", "medium", "low"]} />
        <Filter
          label="Metric"
          value={metricFilter}
          onChange={setMetricFilter}
          options={["all", ...metrics]}
        />
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-500 dark:text-slate-400">Campaign</span>
          <select
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={campaignFilter}
            onChange={(e) => setCampaignFilter(e.target.value)}
          >
            <option value="all">All</option>
            {campaignOptions.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-500 dark:text-slate-400">From</span>
          <input
            type="date"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-500 dark:text-slate-400">To</span>
          <input
            type="date"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-sm"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
        {(campaignFilter !== "all" || dateFrom || dateTo) && (
          <button
            onClick={() => {
              setCampaignFilter("all");
              setDateFrom("");
              setDateTo("");
            }}
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            Clear
          </button>
        )}
        <div className="ml-auto text-xs text-slate-400 dark:text-slate-500">
          {filtered.length} of {anomalies.length} anomalies
        </div>
      </div>

      {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}

      <div className="card overflow-x-auto">
        {loading ? (
          <div className="p-6 text-sm text-slate-500 dark:text-slate-400">Loading anomalies…</div>
        ) : filtered.length === 0 ? (
          <div className="p-6 text-sm text-slate-500 dark:text-slate-400">No anomalies match these filters.</div>
        ) : (
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-xs uppercase text-slate-400 dark:text-slate-500">
                <Th onClick={() => toggleSort("campaign")}>Campaign{sortIndicator("campaign")}</Th>
                <Th onClick={() => toggleSort("metric")}>Metric{sortIndicator("metric")}</Th>
                <Th onClick={() => toggleSort("severity")}>Severity{sortIndicator("severity")}</Th>
                <th className="px-4 py-3 font-medium">Root cause</th>
                <Th onClick={() => toggleSort("detected_date")}>Detected{sortIndicator("detected_date")}</Th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr key={a.anomaly_id} className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{a.campaigns?.campaign_name ?? a.campaign_id}</div>
                    <div className="text-xs text-slate-400 dark:text-slate-500">{titleCase(a.campaigns?.platform)}</div>
                  </td>
                  <td className="px-4 py-3">{titleCase(a.metric)}</td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={a.severity} />
                  </td>
                  <td className="px-4 py-3">
                    {a.root_cause_label ? (
                      <span>
                        {titleCase(a.root_cause_label)}{" "}
                        <span className="text-xs text-slate-400 dark:text-slate-500">
                          ({formatPercent((a.root_cause_confidence ?? 0) * 100, 0)})
                        </span>
                      </span>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">Not yet determined</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">{formatDate(a.detected_date)}</td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/anomalies/${a.anomaly_id}`}
                      className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Th({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <th className="cursor-pointer select-none px-4 py-3 font-medium hover:text-slate-600 dark:hover:text-slate-300" onClick={onClick}>
      {children}
    </th>
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
