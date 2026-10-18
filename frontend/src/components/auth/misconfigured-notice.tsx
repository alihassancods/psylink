import { EmptyState } from "@/components/states";
import { SUPABASE_CONFIG_ERROR } from "@/lib/env";

/** Shown instead of a blank login screen when the public env vars are missing or malformed. */
export function MisconfiguredNotice() {
  return (
    <EmptyState
      title="Psylink is not configured"
      description={`${SUPABASE_CONFIG_ERROR ?? "The public environment variables are not set."} Copy frontend/.env.example to frontend/.env.local, fill in NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, then restart npm run dev.`}
    />
  );
}
