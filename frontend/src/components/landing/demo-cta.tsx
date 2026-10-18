import { demoCta } from "@/app/(landing)/content";
import { DemoActions } from "@/components/landing/demo-actions";
import { Section, SectionHeading } from "@/components/landing/section";

/**
 * The page's second and last ask. Same two buttons as the hero and the same shared handler, so the
 * copy of the demo that a visitor starts is identical whichever one they press.
 */
export function DemoCta() {
  return (
    <Section id={demoCta.id} className="border-y border-border bg-card">
      <div className="mx-auto max-w-2xl text-center">
        <SectionHeading>{demoCta.heading}</SectionHeading>
        <p className="mt-3 text-muted-foreground text-pretty">{demoCta.intro}</p>

        <DemoActions className="mt-8 text-left" />

        <p className="mt-3 text-sm text-muted-foreground">{demoCta.note}</p>
      </div>
    </Section>
  );
}
