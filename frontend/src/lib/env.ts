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

function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * `createClient` throws on a malformed URL or an empty key. Checked here, at module scope, so a
 * bad deployment shows the configuration notice instead of an error thrown from an effect.
 */
export const SUPABASE_CONFIG_ERROR: string | null = (() => {
  if (!SUPABASE_URL && !SUPABASE_ANON_KEY) {
    return "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are not set.";
  }
  if (!SUPABASE_URL) return "NEXT_PUBLIC_SUPABASE_URL is not set.";
  if (!SUPABASE_ANON_KEY) return "NEXT_PUBLIC_SUPABASE_ANON_KEY is not set.";
  if (!isHttpUrl(SUPABASE_URL)) return "NEXT_PUBLIC_SUPABASE_URL is not a valid http(s) URL.";
  return null;
})();

export const isSupabaseConfigured = SUPABASE_CONFIG_ERROR === null;

/** Optional: lets the demo buttons sign in without a backend `/demo/login` route. */
export const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD?.trim() || "";
