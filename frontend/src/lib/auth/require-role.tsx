"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorPanel, PageLoading } from "@/components/states";
import { MisconfiguredNotice } from "@/components/auth/misconfigured-notice";
import { ApiError } from "@/lib/api";
import { PATIENT_LANDING, useSession } from "@/lib/auth/session-provider";
import { useConsentQuery } from "@/lib/queries";

/**
 * Route guards. The role always comes from `/auth/me` (a `profiles` row), never from a token
 * claim, and a patient only reaches the app screens once a clinician link exists. Everything is
 * client-side because Supabase sessions live in the browser and there are no Next API routes.
 *
 * The rule that matters: **a redirect is only ever computed from a request that has answered.**
 * The consent check used to fall through to a default of "no consent" while it was still pending,
 * which sent people to /consent before the call had started — and then bounced them back there
 * after they linked, because the guard's copy of the answer was never refreshed.
 */

/**
 * These three are landmark-free on purpose: the guard renders them inside the route group's
 * `<main>`, so giving them their own would nest one landmark in another.
 */
const PANEL_CLASS = "mx-auto w-full max-w-md py-6";

function Misconfigured() {
  return (
    <div className={PANEL_CLASS}>
      <MisconfiguredNotice />
    </div>
  );
}

export function Unprovisioned() {
  const { notice, signOut } = useSession();
  return (
    <div className={PANEL_CLASS}>
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
    </div>
  );
}

/** `/auth/me` failed for a reason other than the session — retry rather than log the person out. */
export function Unavailable() {
  const { notice, refresh } = useSession();
  return (
    <div className={PANEL_CLASS}>
      <ErrorPanel
        title="We could not reach Psylink"
        message={notice ?? "Check your connection and try again."}
        onRetry={() => void refresh()}
        retryLabel="Try again"
      />
    </div>
  );
}

interface RequireRoleProps {
  role: "patient" | "clinician";
  /** Patients must have an active clinician link before the app screens open. */
  requireConsent?: boolean;
  children: React.ReactNode;
}

/**
 * Wraps the page content, not the shell. The header, the "Need help now?" control and the
 * not-emergency-care footer belong on screen while the checks run, and tearing the subtree down
 * would discard an in-progress check-in.
 */
export function RequireRole({ role, requireConsent = false, children }: RequireRoleProps) {
  return (
    <Suspense fallback={<PageLoading label="Loading" />}>
      <RequireRoleInner role={role} requireConsent={requireConsent}>
        {children}
      </RequireRoleInner>
    </Suspense>
  );
}

function RequireRoleInner({ role, requireConsent = false, children }: RequireRoleProps) {
  const { status, profile, hasSession } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  // /consent and /link are how a patient gets a link, so the gate must not trap them there.
  const exempt = pathname === "/consent" || pathname === "/link";
  const wrongRole = status === "authenticated" && profile != null && profile.role !== role;

  // `hasSession`, not `status === "authenticated"`: the link check needs only the access token, so
  // it runs beside /auth/me instead of queueing behind it. Exempt pages skip it entirely.
  const gateConsent = role === "patient" && requireConsent && hasSession && !exempt && !wrongRole;
  const consent = useConsentQuery(gateConsent);

  let redirect: string | null = null;
  if (status === "anonymous") {
    redirect = "/login";
  } else if (wrongRole) {
    redirect = profile?.role === "patient" ? PATIENT_LANDING : "/patients";
  } else if (gateConsent && consent.isSuccess && consent.data.length === 0) {
    redirect = "/consent";
  }

  useEffect(() => {
    if (redirect) router.replace(redirect);
  }, [redirect, router]);

  if (status === "misconfigured") return <Misconfigured />;
  if (status === "unprovisioned") return <Unprovisioned />;
  if (status === "unavailable") return <Unavailable />;
  if (redirect) return <PageLoading label="Redirecting" />;

  if (status !== "authenticated") return <PageLoading label="Loading" />;

  if (gateConsent) {
    if (consent.isPending) return <PageLoading label="Checking your link" />;
    if (consent.isError) {
      return (
        <ErrorPanel
          title="We could not check your link"
          message={
            consent.error instanceof ApiError
              ? consent.error.message
              : "Something went wrong. Please try again."
          }
          onRetry={() => void consent.refetch()}
        />
      );
    }
  }

  return <>{children}</>;
}
