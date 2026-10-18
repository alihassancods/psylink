import { ShieldCheckIcon } from "lucide-react";

import { safety } from "@/app/(landing)/content";
import { CrisisCard } from "@/components/crisis/crisis-card";
import { Section, SectionHeading } from "@/components/landing/section";

/**
 * The section a reviewer and a patient both read, so it lists mechanisms rather than intentions —
 * each line corresponds to something the code does, not a promise.
 *
 * Crisis resources open as an inline disclosure instead of a modal. It is keyboard-operable and
 * crawlable with no JavaScript, and someone in distress should not have to discover, open and then
 * dismiss a dialog to read a phone number.
 */
export function SafetySection() {
  return (
    <Section id={safety.id} label={safety.heading}>
      <div className="max-w-2xl">
        <span className="inline-flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <ShieldCheckIcon aria-hidden="true" className="size-5" />
        </span>
        <SectionHeading className="mt-4">{safety.heading}</SectionHeading>
        <p className="mt-3 text-muted-foreground">{safety.intro}</p>
      </div>

      <ul className="mt-8 grid gap-3 sm:grid-cols-2">
        {safety.bullets.map((bullet) => (
          <li
            key={bullet}
            className="flex gap-3 rounded-xl border border-border bg-card p-4 text-sm text-foreground"
          >
            <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
            {bullet}
          </li>
        ))}
      </ul>

      <div className="mt-8 rounded-xl border-2 border-border bg-muted p-5">
        <p className="text-sm font-medium text-foreground">{safety.emergency}</p>

        <details className="mt-4 group">
          <summary className="inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg border border-border bg-card px-4 text-sm font-medium text-primary hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2">
            {safety.crisisLinkLabel}
            <ChevronIcon />
          </summary>
          <div className="mt-5">
            <CrisisCard variant="help" />
          </div>
        </details>
      </div>
    </Section>
  );
}

/** Disclosure affordance. Hidden from assistive tech; the summary already says what it does. */
function ChevronIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className="ml-2 size-4 shrink-0 transition-transform group-open:rotate-180"
      fill="none"
    >
      <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}
