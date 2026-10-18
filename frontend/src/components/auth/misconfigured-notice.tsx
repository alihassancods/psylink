import { EmptyState } from "@/components/states";

/** Shown instead of a blank login screen when the public env vars are missing. */
export function MisconfiguredNotice() {
  return (
    <EmptyState
      title="Psylink is not configured"
      description="Supabase sign-in needs NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, and the data needs NEXT_PUBLIC_API_URL. Copy frontend/.env.example to frontend/.env.local, fill them in, and restart npm run dev."
    />
  );
}
