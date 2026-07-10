import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "AI Campaign Optimization Copilot",
  description: "Anomaly detection and AI-generated optimization recommendations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <aside className="w-56 shrink-0 border-r border-[var(--border)]">
            <Nav />
          </aside>
          <main className="flex-1 overflow-x-hidden p-6 md:p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
