"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { PageLoading } from "@/components/states";
import { MisconfiguredNotice } from "@/components/auth/misconfigured-notice";
import { Unavailable, Unprovisioned } from "@/lib/auth/require-role";
import { HOME_BY_ROLE, useSession } from "@/lib/auth/session-provider";

/** `/` sends a signed-in person to their own home; everyone else lands on /login. */
export function RoleRedirect() {
  const { status, profile } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;
    if (status === "misconfigured" || status === "unprovisioned" || status === "unavailable") {
      return;
    }
    if (status === "authenticated" && profile) {
      router.replace(HOME_BY_ROLE[profile.role]);
      return;
    }
    router.replace("/login");
  }, [profile, router, status]);

  if (status === "misconfigured") {
    return (
      <main className="mx-auto w-full max-w-md p-6">
        <MisconfiguredNotice />
      </main>
    );
  }
  if (status === "unprovisioned") return <Unprovisioned />;
  if (status === "unavailable") return <Unavailable />;

  return (
    <main className="flex flex-1 items-center justify-center">
      <PageLoading />
    </main>
  );
}
