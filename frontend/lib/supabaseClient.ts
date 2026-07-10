import { createClient } from "@supabase/supabase-js";

const envUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const envAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

if (!envUrl || !envAnonKey) {
  // eslint-disable-next-line no-console
  console.warn(
    "[supabaseClient] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set. " +
      "Copy frontend/.env.local.example to frontend/.env.local and fill them in.",
  );
}

// These pages are "use client" and construct the client at module scope, which
// also runs during Next's server-side prerender pass at build time - a real
// empty string throws inside createClient() and hard-fails `next build` in any
// environment without secrets configured (e.g. a CI dry-run). Falling back to
// a syntactically-valid placeholder keeps the build green; runtime calls still
// fail loudly (network error) if this ever ships without real credentials.
const supabaseUrl = envUrl || "https://placeholder.supabase.co";
const supabaseAnonKey = envAnonKey || "placeholder-anon-key";

// Read-only browser client (anon key). All writes (approve/reject etc.) go
// through the FastAPI backend instead, per the project's write-path contract.
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});
