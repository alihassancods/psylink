"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/auth/session-provider";

/**
 * Clinician chrome. The AI caveat sits in the footer of every clinician screen as a floor note;
 * the specific "AI-generated, verify with the patient" label appears next to AI output itself.
 */
export function ClinicianShell({ children }: { children: React.ReactNode }) {
  const { profile, signOut } = useSession();

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <div className="flex items-center gap-4">
            <Link href="/patients" className="inline-flex min-h-11 items-center text-base font-semibold">
              Psylink
            </Link>
            <nav aria-label="Clinician" className="flex items-center gap-1">
              <Link
                className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                href="/patients"
              >
                Patients
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {profile?.display_name ?? "Clinician"}
            </span>
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">{children}</main>

      <footer className="border-t border-border bg-card">
        <div className="mx-auto w-full max-w-4xl space-y-1 px-4 py-4 text-sm text-muted-foreground">
          <p>Psylink describes what a patient said. It does not assess, diagnose, or treat.</p>
          <p>Everything generated from a check-in is AI-generated — verify it with the patient.</p>
        </div>
      </footer>
    </div>
  );
}
