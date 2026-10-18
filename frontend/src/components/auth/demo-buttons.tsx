"use client";

import { Button } from "@/components/ui/button";
import { useDemoLogin } from "@/lib/auth/use-demo-login";

/**
 * Demo logins on the sign-in screen. The seeded accounts are synthetic data — nobody in them is a
 * real patient — so the buttons say "demo" everywhere they appear. The behaviour lives in
 * `useDemoLogin`, shared with the landing page.
 */
export function DemoButtons() {
  const { pending, error, run } = useDemoLogin();

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
          onClick={() => void run("patient")}
          disabled={pending !== null}
        >
          {pending === "patient" ? "Opening demo…" : "Try as demo patient"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void run("clinician")}
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
