"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorPanel, PageLoading } from "@/components/states";
import { MisconfiguredNotice } from "@/components/auth/misconfigured-notice";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/auth/session-provider";

/**
 * Route guards. The role always comes from `/auth/me` (a `profiles` row), never from a token
 * claim, and a patient only reaches the app screens once a clinician link exists. Everything is
 * client-side because Supabase sessions live in the browser and there are no Next API routes.
 */

function Misconfigured() {
  return (
    <main className="mx-auto w-full max-w-md p-6">
      <MisconfiguredNotice />
    </main>
  );
}

export function Unprovisioned() {
  const { notice, signOut } = useSession();
  return (
    <main className="mx-auto w-full max-w-md p-6">
      <Card>
        <CardHeader>
          <CardTitle>This account is not set up yet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{notice}</p>
          <Button variant="outline" onClick={() => void signOut()}>
            Sign out
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}

/** `/auth/me` failed for a reason other than the session — retry rather than log the person out. */
export function Unavailable() {
  const { notice, refresh } = useSession();
  return (
    <main className="mx-auto w-full max-w-md p-6">
      <ErrorPanel
        title="We could not reach Psylink"
        message={notice ?? "Check your connection and try again."}
        onRetry={() => void refresh()}
        retryLabel="Try again"
      />
    </main>
  );
}

/**
 * `GET /api/consent` answers with the active links; an empty list means "not linked yet". Shared
 * by the guard and the consent screens, so one request serves both.
 */
export function useConsentStatus(enabled = true) {
  const [state, setState] = useState<ConsentState>({
    status: enabled ? "loading" : "ready",
    hasConsent: false,
    links: [],
    message: "",
  });

  const load = useCallback(async () => {
    setState((previous) => ({ ...previous, status: "loading" }));
    try {
      const links = await api.getConsentLinks();
      const newest = links[0];
      setState({
        status: "ready",
        hasConsent: links.length > 0,
        links,
        message: "",
        clinicianName: newest?.clinician_name ?? null,
        grantedAt: newest?.granted_at ?? null,
      });
    } catch (error) {
      setState((previous) => ({
        ...previous,
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "Something went wrong. Please try again.",
      }));
    }
  }, []);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  return { ...state, reload: load };
}

type ConsentState = {
  status: "loading" | "ready" | "error";
  hasConsent: boolean;
  links: Awaited<ReturnType<typeof api.getConsentLinks>>;
  message: string;
  clinicianName?: string | null;
  grantedAt?: string | null;
};

interface RequireRoleProps {
  role: "patient" | "clinician";
  /** Patients must have an active clinician link before the app screens open. */
  requireConsent?: boolean;
  children: React.ReactNode;
}

export function RequireRole({ role, requireConsent = false, children }: RequireRoleProps) {
  return (
    <Suspense fallback={<PageLoading />}>
      <RequireRoleInner role={role} requireConsent={requireConsent}>
        {children}
      </RequireRoleInner>
    </Suspense>
  );
}

function RequireRoleInner({ role, requireConsent, children }: RequireRoleProps) {
  const { status, profile } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  // /consent and /link are how a patient gets a link, so the gate must not trap them.
  const exempt = pathname === "/consent" || pathname === "/link";
  const gateConsent = role === "patient" && requireConsent && status === "authenticated";
  const consent = useConsentStatus(gateConsent);

  let redirect: string | null = null;
  if (status === "anonymous") {
    redirect = "/login";
  } else if (status === "authenticated" && profile && profile.role !== role) {
    redirect = profile.role === "patient" ? "/home" : "/patients";
  } else if (gateConsent && !exempt && consent.status === "ready" && !consent.hasConsent) {
    redirect = "/consent";
  }

  useEffect(() => {
    if (redirect) router.replace(redirect);
  }, [redirect, router]);

  if (status === "misconfigured") return <Misconfigured />;
  if (status === "unprovisioned") return <Unprovisioned />;
  if (status === "unavailable") return <Unavailable />;
  if (redirect) return <PageLoading label="Redirecting" />;

  if (gateConsent && !exempt) {
    if (consent.status === "loading") return <PageLoading label="Checking your link" />;
    if (consent.status === "error") {
      return (
        <main className="mx-auto w-full max-w-md p-6">
          <ErrorPanel
            title="We could not check your link"
            message={consent.message}
            onRetry={() => void consent.reload()}
          />
        </main>
      );
    }
  }

  if (status !== "authenticated") return <PageLoading />;

  return <>{children}</>;
}
