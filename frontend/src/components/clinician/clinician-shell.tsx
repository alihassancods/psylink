"use client";

import Link from "next/link";

import { SkipLink } from "@/components/layout/skip-link";
import { useSession } from "@/lib/auth/session-provider";

/**
 * Clinician chrome. The caveat about model output sits in the footer of every clinician screen as
 * a floor note; the specific "AI-generated, verify with the patient" label appears next to the AI
 * output itself, on each screen that shows it.
 */
export function ClinicianShell({ children }: { children: React.ReactNode }) {
  const { profile, signOut } = useSession();

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <SkipLink />
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3 px-4 py-2">
          <Link href="/patients" className="inline-flex min-h-11 items-center text-base font-semibold">
            Psylink
          </Link>
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {profile?.display_name ?? "Clinician"}
          </span>
        </div>
        <nav aria-label="Clinician" className="border-t border-border">
          <div className="mx-auto flex w-full max-w-4xl gap-1 overflow-x-auto px-2">
            <NavLink href="/patients">Patients</NavLink>
            <NavLink href="/alerts">Alerts</NavLink>
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

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 outline-none">
        {children}
      </main>

      <footer className="border-t border-border bg-card">
        <div className="mx-auto w-full max-w-4xl space-y-1 px-4 py-4 text-sm text-muted-foreground">
          <p>Psylink describes what a patient said. It does not assess, diagnose, or treat.</p>
          <p>Everything generated from a check-in is AI-generated — verify it with the patient.</p>
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
