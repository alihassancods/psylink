/**
 * Public configuration. `NEXT_PUBLIC_*` values are inlined at build time, so they are read
 * once here rather than scattered across components.
 */

function trimSlash(value: string) {
  return value.replace(/\/+$/, "");
}

export const API_BASE_URL = trimSlash(
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000",
);

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() || "";

export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() || "";

export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/** Optional: lets the demo buttons sign in without a backend `/demo/login` route. */
export const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD?.trim() || "";
