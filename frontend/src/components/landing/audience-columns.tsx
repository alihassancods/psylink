import { CheckIcon } from "lucide-react";

import { audiences } from "@/app/(landing)/content";
import { Section } from "@/components/landing/section";

/**
 * What each side gets, limited to what this build does. "Trends over 7, 14, or 30 days" is the range
 * control on the provider screen; "flagged for review" is the wording an alert actually uses.
 */
export function AudienceColumns() {
  return (
    <Section className="border-y border-border bg-card">
      <div className="grid gap-10 md:grid-cols-2 md:gap-8">
        {audiences.columns.map((column) => (
          <div key={column.heading}>
            <h2 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">
              {column.heading}
            </h2>
            <ul className="mt-5 space-y-4">
              {column.points.map((point) => (
                <li key={point.text} className="flex gap-3">
                  <CheckIcon aria-hidden="true" className="mt-1 size-4 shrink-0 text-primary" />
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">{point.lead}</span>
                    {point.text.slice(point.lead.length)}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  );
}
