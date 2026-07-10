"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/anomalies", label: "Anomalies" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/upload", label: "Upload Data" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex h-full flex-col gap-1 p-4">
      <div className="mb-4 px-2">
        <div className="text-sm font-semibold tracking-tight">AI Campaign Copilot</div>
        <div className="text-xs text-slate-500 dark:text-slate-400">Optimization dashboard</div>
      </div>
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              active
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
