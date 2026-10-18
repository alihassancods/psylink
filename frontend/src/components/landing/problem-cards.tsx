import { Card, CardContent } from "@/components/ui/card";
import { problem } from "@/app/(landing)/content";
import { Section, SectionHeading } from "@/components/landing/section";

/**
 * The gap the product sits in, seen from both sides. The heading is the whole argument, so the cards
 * only have to name what each side loses — no invented statistics, no claim about outcomes.
 *
 * The audience is a label, not a heading: naming these as headings would put "For patients" in the
 * document outline twice, once here and once on the columns that follow.
 */
export function ProblemCards() {
  return (
    <Section className="border-y border-border bg-card">
      <SectionHeading>{problem.heading}</SectionHeading>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2 sm:gap-6">
        {problem.cards.map((card) => (
          <li key={card.audience}>
            <Card className="h-full">
              <CardContent className="space-y-2 p-5">
                <p className="text-sm font-medium text-muted-foreground">{card.audience}</p>
                <p className="text-lg text-foreground text-pretty">{card.text}</p>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </Section>
  );
}
