"use client";

import { use } from "react";
import Link from "next/link";

import { AiNote } from "@/components/clinician/ai-note";
import { EvidenceTranscript } from "@/components/clinician/evidence-transcript";
import { RiskBadge } from "@/components/clinician/risk-badge";
import { EmptyState, ErrorPanel, CardListSkeleton } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useApi } from "@/lib/use-api";
import { SYMPTOM_KEYS, normalizeRisk, type SymptomKey } from "@/types/api";

const SYMPTOM_LABELS: Record<SymptomKey, string> = {
  sleep: "Sleep",
  appetite: "Appetite",
  energy: "Energy",
  anxiety: "Anxiety",
  concentration: "Concentration",
  social_withdrawal: "Withdrawing socially",
  irritability: "Irritability",
};

/**
 * One check-in as the clinician sees it: the patient's words with the evidence quote marked, then
 * the structured fields beside it. The quote is placed by offset when the API supplies them and by
 * exact text otherwise; anything it cannot locate is printed separately instead of guessed at.
 */
export function CheckinDetail({ params }: { params: Promise<{ id: string; checkinId: string }> }) {
  const { id, checkinId } = use(params);
  const view = useApi(() => api.getCheckinDetail(id, checkinId), `checkin-${id}-${checkinId}`);
  const detail = view.data;

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <Link
          className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
          href={`/patients/${id}`}
        >
          Back to this patient
        </Link>
        <h1 className="text-lg font-semibold">
          {detail ? formatDateTime(detail.created_at) : "Check-in"}
        </h1>
      </div>

      {view.status === "loading" ? <CardListSkeleton count={2} /> : null}

      {view.status === "error" ? (
        <ErrorPanel
          title="This check-in is not available"
          message={`${view.message} It may have been deleted by the patient, or their consent was withdrawn.`}
          onRetry={() => void view.reload()}
        />
      ) : null}

      {detail ? (
        <>
          <Card>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>Summary</CardTitle>
              <RiskBadge risk={detail.risk} />
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm">{detail.summary ?? "No summary was produced."}</p>
              <p className="text-xs text-muted-foreground">
                {describeStatus(detail.status)}
                {detail.model ? ` · model ${detail.model}` : ""}
                {detail.risk_source ? ` · risk from ${describeSource(detail.risk_source)}` : ""}
                {detail.confidence ? ` · confidence ${detail.confidence}` : ""}
              </p>
            </CardContent>
          </Card>

          <AiNote />

          <Card>
            <CardHeader>
              <CardTitle>The patient&rsquo;s words</CardTitle>
            </CardHeader>
            <CardContent>
              <EvidenceTranscript
                transcript={detail.transcript}
                note={detail.note}
                quote={detail.evidence_quote}
                offsets={
                  typeof detail.evidence_start === "number" &&
                  typeof detail.evidence_end === "number"
                    ? { start: detail.evidence_start, end: detail.evidence_end }
                    : null
                }
              />
              {detail.evidence_quote ? (
                <p className="mt-3 text-xs text-muted-foreground">
                  The marked passage is quoted verbatim from the text above; the pipeline drops any
                  quote it cannot match.
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Structured fields</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-muted-foreground">Mood</dt>
                  <dd className="font-medium">
                    {detail.mood_score === null ? "Not scored" : `${detail.mood_score} / 10`}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Emotions</dt>
                  <dd className="font-medium">
                    {detail.emotions?.length ? detail.emotions.join(", ") : "None recorded"}
                  </dd>
                </div>
              </dl>

              <ul className="grid gap-2 text-sm sm:grid-cols-2">
                {SYMPTOM_KEYS.map((key) => {
                  const value = detail.symptoms?.[key];
                  return (
                    <li
                      key={key}
                      className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
                    >
                      <span className="text-muted-foreground">{SYMPTOM_LABELS[key]}</span>
                      <span className="font-medium">
                        {typeof value === "number" ? `${value} / 3` : "Not stated"}
                      </span>
                    </li>
                  );
                })}
              </ul>

              {detail.risk && normalizeRisk(detail.risk) === "high" ? (
                <p className="text-sm text-risk-high">
                  This one raised an alert. Acknowledge it in the alerts list once you have acted.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </>
      ) : null}

      {view.status === "success" && !detail ? (
        <EmptyState title="Nothing to show" description="This check-in came back empty." />
      ) : null}
    </div>
  );
}

function describeStatus(status: string) {
  switch (status) {
    case "analyzed":
      return "Analysed";
    case "pending":
      return "Waiting for analysis";
    case "analysis_failed":
      return "Analysis did not complete — the words are still exactly what the patient approved";
    default:
      return status;
  }
}

function describeSource(source: string) {
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
      return source;
  }
}
