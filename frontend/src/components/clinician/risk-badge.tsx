import { AlertTriangleIcon, CircleAlertIcon, CircleCheckIcon, OctagonAlertIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { normalizeRisk, type RiskLevel } from "@/types/api";

/**
 * Risk is never carried by colour alone: every level pairs a distinct icon, a word, and a tint.
 * `medium` from the alerts API and `moderate` from the analysis API are the same thing, and this is
 * the one place that reconciles them.
 */
const RISK_PRESENTATION: Record<
  RiskLevel,
  { label: string; Icon: typeof CircleCheckIcon; className: string }
> = {
  low: {
    label: "Low",
    Icon: CircleCheckIcon,
    className: "border-risk-low-border bg-risk-low-surface text-risk-low",
  },
  moderate: {
    label: "Moderate",
    Icon: AlertTriangleIcon,
    className: "border-risk-moderate-border bg-risk-moderate-surface text-risk-moderate",
  },
  high: {
    label: "High",
    Icon: OctagonAlertIcon,
    className: "border-risk-high-border bg-risk-high-surface text-risk-high",
  },
};

export function RiskBadge({
  risk,
  className,
}: {
  risk: string | null | undefined;
  className?: string;
}) {
  const level = normalizeRisk(risk);

  if (!level) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground",
          className,
        )}
        data-risk="none"
      >
        <CircleAlertIcon className="size-3.5" aria-hidden />
        <span>Not analysed</span>
      </span>
    );
  }

  const { label, Icon, className: tone } = RISK_PRESENTATION[level];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        tone,
        className,
      )}
      data-risk={level}
    >
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">Risk level: </span>
      <span>{label}</span>
    </span>
  );
}
