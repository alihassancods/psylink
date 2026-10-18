"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { HOME_BY_ROLE, useSession } from "@/lib/auth/session-provider";
import type { Role } from "@/types/api";

/**
 * One implementation of "start the demo as this role", shared by the login screen and the landing
 * page so the two can drift into different behaviours.
 *
 * `SessionProvider.demoLogin` owns the transport — it tries the backend's demo route and falls back
 * to a Supabase sign-in as the seeded account. This hook only owns the parts a button needs: which
 * role is in flight, a friendly failure to show, and the redirect afterwards.
 *
 * A cold free-tier backend can take the better part of a minute to answer, and this call chain
 * reaches it, so callers are expected to say something while `pending` is set rather than let the
 * button look broken.
 */
export function useDemoLogin() {
  const { demoLogin } = useSession();
  const router = useRouter();
  const [pending, setPending] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** The role of the last failure, so a retry button re-runs the same thing the visitor asked for. */
  const failedRole = useRef<Role | null>(null);

  const run = useCallback(
    async (role: Role) => {
      setPending(role);
      setError(null);
      try {
        const profile = await demoLogin(role);
        router.replace(HOME_BY_ROLE[profile.role]);
      } catch (caught) {
        failedRole.current = role;
        setError(
          caught instanceof ApiError
            ? caught.message
            : "The demo did not start. Please try again.",
        );
        setPending(null);
      }
    },
    [demoLogin, router],
  );

  const retry = useCallback(() => {
    if (failedRole.current) void run(failedRole.current);
  }, [run]);

  return { pending, error, run, retry };
}
