"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";

import { ApiError, request } from "@/lib/api";
import { DEMO_PASSWORD, isSupabaseConfigured } from "@/lib/env";
import { useMeQuery, STALE } from "@/lib/queries";
import { queryKeys } from "@/lib/query-keys";
import { getSupabaseClient } from "@/lib/supabase";
import type { AuthMe, Role } from "@/types/api";

export type AuthStatus =
  | "loading"
  | "authenticated"
  | "anonymous"
  /** Signed in but Psylink could not read the profile (backend answered 401 for a live session). */
  | "unprovisioned"
  /** Signed in but the profile read failed for another reason (network or 5xx). */
  | "unavailable"
  | "misconfigured";

/** Emails seeded by `backend/scripts/seed_demo.py --create-auth-users`. All synthetic. */
export const DEMO_EMAILS: Record<Role, string> = {
  patient: "demo.patient.stable@bridge.example",
  clinician: "demo.clinician@bridge.example",
};

/** Where a patient lands after sign-in. */
export const PATIENT_LANDING = "/home";

export const HOME_BY_ROLE: Record<Role, string> = {
  patient: PATIENT_LANDING,
  clinician: "/patients",
};

/** Whether Supabase handed us a session. Kept separate from the profile read below it. */
type SessionPhase = "unknown" | "anonymous" | "present";

interface SessionValue {
  status: AuthStatus;
  profile: AuthMe | null;
  /**
   * Supabase holds a session. Lets the consent check start alongside `/auth/me` instead of waiting
   * behind it — those two calls only need the token, and serialising them cost a round trip before
   * the first pixel of app content.
   */
  hasSession: boolean;
  /** Populated when Supabase is fine but the profile row is missing. */
  notice: string | null;
  signIn: (email: string, password: string) => Promise<AuthMe>;
  /** Self-service signup can only create patients — see the RLS insert policy. */
  signUpPatient: (input: {
    email: string;
    password: string;
    displayName: string;
  }) => Promise<{ needsEmailConfirmation: boolean }>;
  signOut: () => Promise<void>;
  /** @see demoLogin — kept on the context so the login screen stays presentational. */
  demoLogin: (role: Role) => Promise<AuthMe>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

function friendlyAuthMessage(message: string) {
  const lower = message.toLowerCase();
  if (lower.includes("invalid login credentials")) {
    return "That email and password do not match.";
  }
  if (lower.includes("email not confirmed")) {
    return "Confirm your email address first, then sign in.";
  }
  return message;
}

/** A 401 from `/auth/me` while Supabase holds a session means "no profile row", not "signed out". */
function isMissingProfile(error: unknown) {
  return error instanceof ApiError && error.status === 401;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [sessionPhase, setSessionPhase] = useState<SessionPhase>(
    isSupabaseConfigured ? "unknown" : "anonymous",
  );

  /**
   * Identity is a cached query, not a `useState` written from an auth callback. Supabase fires
   * `INITIAL_SESSION` and `SIGNED_IN` around the same tick, so the previous version asked for
   * `/auth/me` twice per sign-in; invalidating one key lets the cache absorb the duplicates.
   */
  const meQuery = useMeQuery(sessionPhase === "present");

  const readMe = useCallback(async (): Promise<AuthMe> => {
    const me = await queryClient.fetchQuery({
      queryKey: queryKeys.me,
      queryFn: () => request<AuthMe>("/auth/me", { redirectOnUnauthenticated: false }),
      staleTime: STALE.me,
      retry: false,
    });
    setSessionPhase("present");
    return me;
  }, [queryClient]);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    // Supabase fires INITIAL_SESSION on subscribe, so the first read happens in this callback
    // rather than as a synchronous setState in the effect body. A malformed URL or empty key is
    // caught at module scope in env.ts, so building the client cannot throw here.
    const subscription = getSupabaseClient().auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT" || (event === "INITIAL_SESSION" && !session)) {
        setSessionPhase("anonymous");
        return;
      }
      if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
        if (!session) return;
        setSessionPhase("present");
        // TOKEN_REFRESHED is deliberately ignored: a new token never changes the profile row.
        queryClient.invalidateQueries({ queryKey: queryKeys.me });
      }
    });
    return () => {
      subscription.data.subscription?.unsubscribe();
    };
  }, [queryClient]);

  const status: AuthStatus = (() => {
    if (!isSupabaseConfigured) return "misconfigured";
    if (sessionPhase === "unknown") return "loading";
    if (sessionPhase === "anonymous") return "anonymous";
    if (meQuery.isPending) return "loading";
    if (meQuery.isError) return isMissingProfile(meQuery.error) ? "unprovisioned" : "unavailable";
    return "authenticated";
  })();

  const notice = useMemo<string | null>(() => {
    if (status === "unprovisioned") {
      return "You are signed in, but this account has no Psylink profile yet. A clinician profile is created by your care service; patients can create one from Sign up.";
    }
    if (status === "unavailable") {
      // A dead backend is not "signed out": say so and offer a retry.
      return meQuery.error instanceof ApiError
        ? meQuery.error.message
        : "We could not reach Psylink. Check your connection and try again.";
    }
    return null;
  }, [status, meQuery.error]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { error } = await getSupabaseClient().auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) throw new ApiError(401, "sign_in_failed", friendlyAuthMessage(error.message));
      let me: AuthMe;
      try {
        me = await readMe();
      } catch (caught) {
        if (isMissingProfile(caught)) {
          throw new ApiError(
            401,
            "no_profile",
            "Signed in, but this account has no Psylink profile yet.",
          );
        }
        throw caught;
      }
      return me;
    },
    [readMe],
  );

  const signUpPatient = useCallback(
    async (input: { email: string; password: string; displayName: string }) => {
      const supabase = getSupabaseClient();
      const { data, error } = await supabase.auth.signUp({
        email: input.email.trim(),
        password: input.password,
        options: { data: { display_name: input.displayName } },
      });
      if (error) throw new ApiError(400, "sign_up_failed", friendlyAuthMessage(error.message));

      const user = data.user;
      const session = data.session as Session | null;
      if (user && session) {
        // RLS lets a caller insert only their own profile, and only as a patient.
        const { error: profileError } = await supabase
          .from("profiles")
          .insert({ id: user.id, role: "patient", display_name: input.displayName });
        if (profileError) {
          throw new ApiError(
            400,
            "profile_insert_failed",
            "We could not create your Psylink profile. If you already have an account, log in instead.",
          );
        }
        await readMe();
        return { needsEmailConfirmation: false };
      }
      return { needsEmailConfirmation: true };
    },
    [readMe],
  );

  const signOut = useCallback(async () => {
    if (isSupabaseConfigured) await getSupabaseClient().auth.signOut();
    // Every cached transcript, summary and alert belongs to the person who just left.
    queryClient.clear();
    setSessionPhase("anonymous");
    // No `router.replace` here: the guard owns redirects, and it sends an anonymous visitor to
    // /login. Asking for the same navigation twice is how the login screen used to double-render.
  }, [queryClient]);

  /**
   * The spec asks for `POST /demo/login {role}`. The backend has no such route today, so this
   * tries it first and, when it is missing, falls back to a normal Supabase sign-in as the
   * seeded demo account. If `NEXT_PUBLIC_DEMO_PASSWORD` is not set, it says so plainly rather
   * than pretending.
   */
  const demoLogin = useCallback(
    async (role: Role) => {
      try {
        const result = await request<{ access_token?: string }>("/demo/login", {
          method: "POST",
          json: { role },
          redirectOnUnauthenticated: false,
        });
        if (result?.access_token) {
          await getSupabaseClient().auth.setSession({
            access_token: result.access_token,
            refresh_token: "",
          });
          const me = await readMe();
          if (me) return me;
        }
      } catch {
        // Route absent in this deployment — fall through to the seeded demo credentials.
      }

      if (!DEMO_PASSWORD) {
        throw new ApiError(
          0,
          "demo_unavailable",
          "Demo logins are not available in this deployment: the backend has no /demo/login route and no demo password is configured.",
        );
      }
      return signIn(DEMO_EMAILS[role], DEMO_PASSWORD);
    },
    [readMe, signIn],
  );

  const refresh = useCallback(async () => {
    if (!isSupabaseConfigured) return;
    const { data } = await getSupabaseClient().auth.getSession();
    if (!data.session) {
      setSessionPhase("anonymous");
      return;
    }
    setSessionPhase("present");
    queryClient.invalidateQueries({ queryKey: queryKeys.me });
  }, [queryClient]);

  const value = useMemo<SessionValue>(
    () => ({
      status,
      profile: meQuery.data ?? null,
      hasSession: sessionPhase === "present",
      notice,
      signIn,
      signUpPatient,
      signOut,
      demoLogin,
      refresh,
    }),
    [status, meQuery.data, sessionPhase, notice, signIn, signUpPatient, signOut, demoLogin, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside <SessionProvider>");
  return context;
}
