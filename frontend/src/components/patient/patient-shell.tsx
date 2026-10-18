"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PATIENT_LANDING, useSession } from "@/lib/auth/session-provider";

/**
 * Patient chrome. One primary action per screen; the "Need help now?" control and the
 * not-emergency-care footer live here so every patient screen inherits them.
 */
export function PatientShell({ children }: { children: React.ReactNode }) {
  const { profile, signOut } = useSession();

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <Link
            href={PATIENT_LANDING}
            className="inline-flex min-h-11 items-center text-base font-semibold"
          >
            Psylink
          </Link>
          <nav aria-label="Account" className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          </nav>
        </div>
      </header>

      <div className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
        <p className="pb-4 text-sm text-muted-foreground">
          Hello{profile?.display_name ? `, ${profile.display_name}` : ""}. Only your psychologist
          or psychiatrist sees what you share.
        </p>
        {children}
      </div>

      <footer className="border-t border-border bg-card">
        <div className="mx-auto w-full max-w-2xl space-y-1 px-4 py-4 text-sm text-muted-foreground">
          <p>Psylink is not emergency care.</p>
          <p>If you are in danger, contact your local emergency services.</p>
        </div>
      </footer>
    </div>
  );
}
