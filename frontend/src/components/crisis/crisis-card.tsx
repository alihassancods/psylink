import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CRISIS_RESOURCES } from "@/config/crisis-resources";

/**
 * The crisis card. Prominent without being alarming: no red, no risk label, no diagnosis — it
 * appears both after a check-in that says "show resources" and from the "Need help now?" control on
 * every patient screen.
 */
export function CrisisCard({ variant = "result" }: { variant?: "result" | "help" }) {
  return (
    <Card className="border-2 border-primary bg-risk-low-surface">
      <CardHeader>
        <CardTitle className="text-lg">{CRISIS_RESOURCES.headline}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-foreground">{CRISIS_RESOURCES.intro}</p>

        <ol className="list-decimal space-y-2 pl-5 text-foreground">
          {CRISIS_RESOURCES.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>

        <ul className="space-y-2">
          {CRISIS_RESOURCES.resources.map((resource) => (
            <li key={resource.label} className="rounded-lg border border-border bg-card p-3">
              <p className="font-medium">{resource.label}</p>
              <p className="text-muted-foreground">{resource.detail}</p>
            </li>
          ))}
        </ul>

        <p className="text-xs text-muted-foreground">
          {variant === "help"
            ? "You can read this at any time — it is a link in the header of every page here."
            : CRISIS_RESOURCES.closing}
        </p>
      </CardContent>
    </Card>
  );
}
