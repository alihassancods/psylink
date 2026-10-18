"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { CrisisCard } from "@/components/crisis/crisis-card";
import { PATIENT_LANDING, useSession } from "@/lib/auth/session-provider";

/**
 * Patient chrome. The "Need help now?" control and the not-emergency-care footer live here, so
 * every patient screen inherits them — nobody has to be mid-check-in to find them.
 */
export function PatientShell({ children }: { children: React.ReactNode }) {
  const { profile, signOut } = useSession();
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-2xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <Link
            href={PATIENT_LANDING}
            className="inline-flex min-h-11 items-center text-base font-semibold"
          >
            Psylink
          </Link>
          <nav aria-label="Patient" className="flex items-center gap-1">
            <Link
              className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              href="/checkin"
            >
              Check-in
            </Link>

            <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" className="font-semibold text-primary">
                  Need help now?
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[85dvh] overflow-y-auto p-0">
                <DialogHeader className="p-4 pb-0">
                  <DialogTitle className="sr-only">Crisis support</DialogTitle>
                  <DialogDescription className="sr-only">
                    Ways to reach a person or service that can respond right now.
                  </DialogDescription>
                </DialogHeader>
                <div className="p-4">
                  <CrisisCard variant="help" />
                </div>
              </DialogContent>
            </Dialog>

            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          </nav>
        </div>
      </header>

      <div className="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
        <p className="pb-4 text-sm text-muted-foreground">
          Hello{profile?.display_name ? `, ${profile.display_name}` : ""}. Only your psychologist or
          psychiatrist sees what you share.
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
