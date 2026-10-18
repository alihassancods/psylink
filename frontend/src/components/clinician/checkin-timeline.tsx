import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskBadge } from "@/components/clinician/risk-badge";
import { formatDateTime } from "@/lib/utils";
import type { TrendPoint } from "@/types/api";

/**
 * Check-ins in range, newest first, each opening the full record. A trend point carries the mood
 * score and summary; the detail screen carries the transcript and evidence.
 */
export function CheckinTimeline({
  patientId,
  points,
}: {
  patientId: string;
  points: TrendPoint[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Check-ins in this range</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {points.length === 0 ? (
          <p className="text-sm text-muted-foreground">No check-ins in this range.</p>
        ) : null}

        <ol className="space-y-3">
          {points.map((point) => (
            <li key={point.checkin_id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium">{formatDateTime(point.created_at)}</p>
                <RiskBadge risk={point.risk} />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {point.summary ?? "No summary — the analysis did not complete for this one."}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Mood {point.mood_score === null ? "not scored" : `${point.mood_score}/10`}
                {point.risk_source ? ` · from ${describeSource(point.risk_source)}` : ""}
              </p>
              <Link
                className="mt-2 inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
                href={`/patients/${patientId}/checkins/${point.checkin_id}`}
              >
                Open check-in
              </Link>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function describeSource(source: string | null): string {
  switch (source) {
    case "keyword":
      return "the keyword screen only";
    case "llm":
      return "the model";
    case "both":
      return "the screen and the model";
    case "fallback":
      return "a fail-safe, not an assessment";
    default:
      return "an unknown source";
  }
}
