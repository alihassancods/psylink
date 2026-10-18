"use client";

import { Button } from "@/components/ui/button";
import { demoButtons } from "@/app/(landing)/content";
import { useDemoLogin } from "@/lib/auth/use-demo-login";
import { cn } from "@/lib/utils";

/**
 * "Try as patient" and "Try as psychologist". The page's only real call to action, used in the hero
 * and again in the demo section.
 *
 * The first click can take a while — a cold free-tier backend has to wake before it can answer — so
 * the pressed button says what is happening instead of looking dead, and a failure offers a retry
 * rather than leaving the visitor guessing.
 */
export function DemoActions({ className }: { className?: string }) {
  const { pending, error, run, retry } = useDemoLogin();

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          type="button"
          size="lg"
          className="flex-1"
          onClick={() => void run("patient")}
          disabled={pending !== null}
          aria-busy={pending === "patient"}
        >
          {pending === "patient" ? demoButtons.waitingLabel : demoButtons.patientLabel}
        </Button>
        <Button
          type="button"
          size="lg"
          variant="outline"
          className="flex-1"
          onClick={() => void run("clinician")}
          disabled={pending !== null}
          aria-busy={pending === "clinician"}
        >
          {pending === "clinician" ? demoButtons.waitingLabel : demoButtons.psychologistLabel}
        </Button>
      </div>

      {error ? (
        <div role="alert" className="space-y-2 rounded-lg border border-border bg-muted p-3">
          <p className="text-sm text-foreground">{error}</p>
          <Button type="button" size="sm" variant="outline" onClick={retry}>
            {demoButtons.retryLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
