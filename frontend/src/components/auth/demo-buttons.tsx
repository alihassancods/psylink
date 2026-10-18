"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { HOME_BY_ROLE, useSession } from "@/lib/auth/session-provider";
import type { Role } from "@/types/api";

/**
 * Demo logins. The seeded accounts are synthetic data — nobody in them is a real patient — so
 * the buttons say "demo" everywhere they appear.
 */
export function DemoButtons() {
  const { demoLogin } = useSession();
  const router = useRouter();
  const [pending, setPending] = useState<Role | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onDemo(role: Role) {
    setPending(role);
    setError(null);
    try {
      const profile = await demoLogin(role);
      router.replace(HOME_BY_ROLE[profile.role]);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Demo login did not work on this deployment.",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <p className="text-sm font-medium">Look around first</p>
      <p className="text-xs text-muted-foreground">
        Demo accounts hold synthetic data only — no real patient audio or text.
      </p>
      <div className="grid gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => void onDemo("patient")}
          disabled={pending !== null}
        >
          {pending === "patient" ? "Opening demo…" : "Try as demo patient"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void onDemo("clinician")}
          disabled={pending !== null}
        >
          {pending === "clinician" ? "Opening demo…" : "Try as demo psychologist"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
