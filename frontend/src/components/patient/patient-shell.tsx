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
import { SkipLink } from "@/components/layout/skip-link";
import { CrisisCard } from "@/components/crisis/crisis-card";
import { PATIENT_LANDING, useSession } from "@/lib/auth/session-provider";

/**
 * Patient chrome. The "Need help now?" control and the not-emergency-care footer live here, so
 * every patient screen inherits them — nobody has to be mid-check-in to find them. The nav is its
 * own row so the help control stays visible at 360px instead of pushing it off screen.
 */
export function PatientShell({ children }: { children: React.ReactNode }) {
  const { profile, signOut } = useSession();
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <SkipLink />
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-2">
          <Link
            href={PATIENT_LANDING}
            className="inline-flex min-h-11 items-center text-base font-semibold"
          >
            Psylink
          </Link>
          <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="shrink-0 font-semibold text-primary">
                Need help now?
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[85dvh] overflow-y-auto p-0">
              <DialogHeader className="p-4 pb-0">
                <DialogTitle className="sr-only">Crisis support</DialogTitle>
                <DialogDescription className="sr-only">
                  Ways to reach a person or a service that can respond right now.
                </DialogDescription>
              </DialogHeader>
              <div className="p-4">
                <CrisisCard variant="help" />
              </div>
            </DialogContent>
          </Dialog>
        </div>

        <nav aria-label="Patient" className="border-t border-border">
          <div className="mx-auto flex w-full max-w-2xl gap-1 overflow-x-auto px-2">
            <NavLink href="/home">Home</NavLink>
            <NavLink href="/checkin">Check-in</NavLink>
            <NavLink href="/history">History</NavLink>
            <NavLink href="/settings">Settings</NavLink>
            <button
              type="button"
              onClick={() => void signOut()}
              className="inline-flex min-h-11 shrink-0 items-center rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        </nav>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-2xl flex-1 px-4 py-6 outline-none">
        <p className="pb-4 text-sm text-muted-foreground">
          Hello{profile?.display_name ? `, ${profile.display_name}` : ""}. Only your psychologist or
          psychiatrist sees what you share.
        </p>
        {children}
      </main>

      <footer className="border-t border-border bg-card">
        <div className="mx-auto w-full max-w-2xl space-y-1 px-4 py-4 text-sm text-muted-foreground">
          <p>Psylink is not emergency care.</p>
          <p>If you are in danger, contact your local emergency services.</p>
        </div>
      </footer>
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      className="inline-flex min-h-11 shrink-0 items-center rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
      href={href}
    >
      {children}
    </Link>
  );
}
