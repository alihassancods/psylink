import { faq } from "@/app/(landing)/content";
import { Section, SectionHeading } from "@/components/landing/section";

/**
 * Questions a judge, a patient and a provider all ask, answered against this build — including the
 * two honest negatives: it is not validated, and alerts are not real-time.
 *
 * Native `<details>`/`<summary>` rather than an accordion component: it is focusable, opens on Enter
 * or Space, and needs no JavaScript and no extra dependency, which matters on a page whose whole job
 * is to load fast enough to be judged in ten seconds.
 */
export function Faq() {
  return (
    <Section id={faq.id} label={faq.heading}>
      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:gap-12">
        <SectionHeading className="md:text-3xl">{faq.heading}</SectionHeading>

        <dl className="divide-y divide-border border-y border-border">
          {faq.items.map((item) => (
            <div key={item.question} className="group py-1">
              <details>
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-3 text-left text-base font-medium text-foreground hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2">
                  {item.question}
                  <PlusIcon />
                </summary>
                <dd className="pb-4 pr-8 text-muted-foreground text-pretty">{item.answer}</dd>
              </details>
            </div>
          ))}
        </dl>
      </div>
    </Section>
  );
}

function PlusIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-45"
      fill="none"
    >
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}
