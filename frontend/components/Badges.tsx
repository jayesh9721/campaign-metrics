import { titleCase } from "@/lib/format";

const SEVERITY_CLASSES: Record<string, string> = {
  high: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-800",
  medium:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 border-amber-300 dark:border-amber-800",
  low: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700",
};

export function SeverityBadge({ severity }: { severity: string | null | undefined }) {
  const cls = SEVERITY_CLASSES[severity ?? ""] ?? SEVERITY_CLASSES.low;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {titleCase(severity) || "Unknown"}
    </span>
  );
}

const STATUS_CLASSES: Record<string, string> = {
  pending:
    "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 border-blue-300 dark:border-blue-800",
  approved:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800",
  rejected:
    "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-800",
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const cls = STATUS_CLASSES[status ?? ""] ?? STATUS_CLASSES.pending;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {titleCase(status) || "Pending"}
    </span>
  );
}

const TYPE_CLASSES: Record<string, string> = {
  budget: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 border-violet-300 dark:border-violet-800",
  bidding: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300 border-cyan-300 dark:border-cyan-800",
  creative: "bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300 border-pink-300 dark:border-pink-800",
};

export function TypeBadge({ type }: { type: string | null | undefined }) {
  const cls = TYPE_CLASSES[type ?? ""] ?? TYPE_CLASSES.budget;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {titleCase(type) || "—"}
    </span>
  );
}
