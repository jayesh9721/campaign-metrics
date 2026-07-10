"use client";

import { useCallback, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

interface UploadResult {
  campaigns: number;
  daily_metrics: number;
  rows_skipped: number;
}

export default function UploadPage() {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!API_URL) {
      setError("NEXT_PUBLIC_API_URL is not configured.");
      return;
    }
    setUploading(true);
    setError(null);
    setResult(null);
    setFileName(file.name);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/jobs/upload-csv`, { method: "POST", body: formData });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail ?? `Upload failed with status ${res.status}`);
      setResult(body as UploadResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload Data</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Manually import campaign performance from a spreadsheet — it lands in the same normalized schema
          every connector writes to, so anomaly detection and recommendations run over it identically.
        </p>
      </div>

      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className="card flex flex-col items-center justify-center gap-3 border-2 border-dashed border-[var(--border)] p-10 text-center"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
        <div className="text-sm text-slate-500 dark:text-slate-400">Drag a CSV file here, or</div>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          {uploading ? "Uploading…" : "Choose file"}
        </button>
        {fileName && !uploading && <div className="text-xs text-slate-400 dark:text-slate-500">Last file: {fileName}</div>}
      </div>

      {error && <div className="card p-4 text-sm text-red-600 dark:text-red-400">{error}</div>}

      {result && (
        <div className="card p-5">
          <div className="font-medium">Import complete</div>
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <div className="text-lg font-semibold">{result.campaigns}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">campaigns created/updated</div>
            </div>
            <div>
              <div className="text-lg font-semibold">{result.daily_metrics}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">daily metric rows imported</div>
            </div>
            <div>
              <div className="text-lg font-semibold">{result.rows_skipped}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">rows skipped (missing date/campaign_id)</div>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Run <span className="font-mono">Sync Now</span> on the Dashboard, or wait for the next automated
            cycle, to detect anomalies and generate recommendations over this data.
          </p>
        </div>
      )}

      <div className="card p-5">
        <div className="font-medium">Expected columns</div>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Required: <span className="font-mono">campaign_id, campaign_name, platform, date, impressions, clicks, spend</span>.
          Optional: <span className="font-mono">brand, account_id, objective, bid_strategy, status, start_date, budget_cap,
          budget_type, conversions, revenue, frequency, ctr, cpc, conversion_rate, roas, cpa</span> — anything
          omitted (ctr, cpc, conversion_rate, roas, cpa) is computed automatically from the raw numbers.
        </p>
        <a
          href="/sample-campaign-data.csv"
          download
          className="mt-3 inline-block text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          Download a sample CSV →
        </a>
      </div>
    </div>
  );
}
