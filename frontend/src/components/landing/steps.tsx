import { CalendarDaysIcon, ChartLineIcon, MicIcon, PencilLineIcon } from "lucide-react";

import { howItWorks } from "@/app/(landing)/content";
import { Section, SectionHeading } from "@/components/landing/section";

/** content.ts names glyphs as plain strings; they become components here so the copy file stays data. */
const ICONS = {
  mic: MicIcon,
  pencil: PencilLineIcon,
  chart: ChartLineIcon,
  calendar: CalendarDaysIcon,
} as const;

/**
 * Four steps, in order, and the second one is the point: the person reads their own words before
 * anything is sent. Numbered as an ordered list so the sequence survives a screen reader.
 */
export function Steps() {
  return (
    <Section id={howItWorks.id} label={howItWorks.heading}>
      <SectionHeading>{howItWorks.heading}</SectionHeading>

      <ol className="mt-8 grid gap-4 sm:grid-cols-2 sm:gap-6 lg:grid-cols-4">
        {howItWorks.steps.map((step, index) => {
          const Icon = ICONS[step.icon as keyof typeof ICONS];
          return (
            <li key={step.title} className="rounded-xl border border-border bg-card p-5">
              <span className="inline-flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon aria-hidden="true" className="size-5" />
              </span>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                <span className="text-muted-foreground">{index + 1}. </span>
                {step.title}: {step.text}
              </h3>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
