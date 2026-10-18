"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session } from "@supabase/supabase-js";

import { ApiError, request } from "@/lib/api";
import { DEMO_PASSWORD, isSupabaseConfigured } from "@/lib/env";
import { getSupabaseClient } from "@/lib/supabase";
import type { AuthMe, Role } from "@/types/api";

export type AuthStatus =
  | "loading"
  | "authenticated"
  | "anonymous"
  | "unprovisioned"
  /** Signed in but Psylink could not read the profile (network or 5xx). */
  | "unavailable"
  | "misconfigured";

/** Emails seeded by `backend/scripts/seed_demo.py --create-auth-users`. All synthetic. */
export const DEMO_EMAILS: Record<Role, string> = {
  patient: "demo.patient.stable@bridge.example",
  clinician: "demo.clinician@bridge.example",
};

export const HOME_BY_ROLE: Record<Role, string> = {
  patient: "/home",
  clinician: "/patients",
};

interface SessionValue {
  status: AuthStatus;
  profile: AuthMe | null;
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

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>(
    isSupabaseConfigured ? "loading" : "misconfigured",
  );
  const [profile, setProfile] = useState<AuthMe | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  /** The backend resolves the role from `profiles`, so identity is always re-read from it. */
  const loadProfile = useCallback(async () => {
    try {
      const me = await request<AuthMe>("/auth/me", {
        redirectOnUnauthenticated: false,
      });
      setProfile(me);
      setNotice(null);
      setStatus("authenticated");
      return me;
    } catch (error) {
      setProfile(null);
      if (error instanceof ApiError && error.status === 401) {
        setStatus("unprovisioned");
        setNotice(
          "You are signed in, but this account has no Psylink profile yet. A clinician profile is created by your care service; patients can create one from Sign up.",
        );
      } else {
        // A dead backend is not "signed out": say so and offer a retry.
        setStatus("unavailable");
        setNotice(
          error instanceof ApiError
            ? error.message
            : "We could not reach Psylink. Check your connection and try again.",
        );
      }
      return null;
    }
  }, []);

  const hydrate = useCallback(async () => {
    if (!isSupabaseConfigured) return;
    const { data } = await getSupabaseClient().auth.getSession();
    if (!data.session) {
      setStatus("anonymous");
      setProfile(null);
      return;
    }
    await loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    // Supabase fires INITIAL_SESSION on subscribe, so the first read happens in this callback
    // rather than as a synchronous setState in the effect body.
    const subscription = getSupabaseClient().auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT" || (event === "INITIAL_SESSION" && !session)) {
        setStatus("anonymous");
        setProfile(null);
        return;
      }
      if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED" || event === "INITIAL_SESSION") {
        if (session) void loadProfile();
      }
    });
    return () => {
      subscription.data.subscription?.unsubscribe();
    };
  }, [loadProfile]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { error } = await getSupabaseClient().auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) throw new ApiError(401, "sign_in_failed", friendlyAuthMessage(error.message));
      const me = await loadProfile();
      if (!me) {
        throw new ApiError(
          401,
          "no_profile",
          "Signed in, but this account has no Psylink profile yet.",
        );
      }
      return me;
    },
    [loadProfile],
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
        await loadProfile();
        return { needsEmailConfirmation: false };
      }
      return { needsEmailConfirmation: true };
    },
    [loadProfile],
  );

  const signOut = useCallback(async () => {
    if (isSupabaseConfigured) await getSupabaseClient().auth.signOut();
    setProfile(null);
    setStatus("anonymous");
    router.replace("/login");
  }, [router]);

  /**
   * The spec asks for `POST /demo/login {role}`. The backend has no such route today, so this
   * tries it first and, when it is missing, falls back to a normal Supabase sign-in as the
   * seeded demo account. If `NEXT_PUBLIC_DEMO_PASSWORD` is not set, it says so plainly rather
   * than pretending.
   */
  const demoLogin = useCallback(
    async (role: Role) => {
      try {
        const result = await request<{ access_token?: string }>(
          "/demo/login",
          { method: "POST", json: { role }, redirectOnUnauthenticated: false },
        );
        if (result?.access_token) {
          await getSupabaseClient().auth.setSession({
            access_token: result.access_token,
            refresh_token: "",
          });
          const me = await loadProfile();
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
    [loadProfile, signIn],
  );

  const value = useMemo<SessionValue>(
    () => ({
      status,
      profile,
      notice,
      signIn,
      signUpPatient,
      signOut,
      demoLogin,
      refresh: hydrate,
    }),
    [status, profile, notice, signIn, signUpPatient, signOut, demoLogin, hydrate],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside <SessionProvider>");
  return context;
}
