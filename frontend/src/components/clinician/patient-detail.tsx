"use client";

import { use, useState } from "react";
import Link from "next/link";

import { AiNote } from "@/components/clinician/ai-note";
import { CheckinTimeline } from "@/components/clinician/checkin-timeline";
import { EmotionBars } from "@/components/charts/emotion-bars";
import { MoodTrendChart } from "@/components/charts/mood-trend-chart";
import { SymptomMultiples } from "@/components/charts/symptom-multiples";
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import type { CheckinDetail, Trend } from "@/types/api";

const RANGES = [7, 14, 30] as const;
type Range = (typeof RANGES)[number];

/**
 * Trend requests carry mood, risk and summary only. Symptoms and emotions live on the individual
 * analysis, so the most recent records are fetched to build those charts. Capped at 20 because each
 * one is a request; the page says so rather than implying the chart covers the whole range.
 */
const DETAIL_LIMIT = 20;

export function PatientDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [days, setDays] = useState<Range>(14);

  const view = useApi(
    async (): Promise<{ trend: Trend; details: CheckinDetail[]; name: string | null }> => {
      const [trend, roster] = await Promise.all([
        api.getPatientTrends(id, days),
        api.listPatients().then(
          (page) => page,
          () => null,
        ),
      ]);
      const recent = trend.points.slice(0, DETAIL_LIMIT);
      const rows = await Promise.all(
        recent.map((point) =>
          api.getCheckinDetail(id, point.checkin_id).then(
            (detail) => detail,
            () => null,
          ),
        ),
      );
      return {
        trend,
        details: rows.filter((row): row is CheckinDetail => row !== null),
        name: roster?.items.find((patient) => patient.patient_id === id)?.display_name ?? null,
      };
    },
    `patient-${id}-${days}`,
  );

  const trend = view.data?.trend;
  const points = trend?.points ?? [];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <Link
          className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
          href="/patients"
        >
          All patients
        </Link>
        <h1 className="text-lg font-semibold">{view.data?.name ?? "This patient"}</h1>
        <p className="text-sm text-muted-foreground">
          Only what this patient chose to share, and only while their consent is active.
        </p>
      </div>

      <RangeSwitcher days={days} onChange={setDays} />

      {view.status === "loading" ? <CardListSkeleton count={3} /> : null}

      {view.status === "error" ? (
        <ErrorPanel
          title="This patient is not available"
          message={`${view.message} If they revoked consent, their history closes immediately.`}
          onRetry={() => void view.reload()}
        />
      ) : null}

      {view.status === "success" && points.length === 0 ? (
        <EmptyState
          title="No check-ins in this range"
          description="Nothing was shared in the last few days. Widen the range, or check back after the next check-in."
        />
      ) : null}

      {trend ? (
        <>
          <ul className="grid gap-2 text-sm sm:grid-cols-3">
            <li className="rounded-lg border border-border bg-card p-3">
              <span className="block text-xs text-muted-foreground">High risk</span>
              <span className="font-semibold">{trend.high_count}</span>
            </li>
            <li className="rounded-lg border border-border bg-card p-3">
              <span className="block text-xs text-muted-foreground">Moderate</span>
              <span className="font-semibold">{trend.moderate_count}</span>
            </li>
            <li className="rounded-lg border border-border bg-card p-3">
              <span className="block text-xs text-muted-foreground">Analysis missing</span>
              <span className="font-semibold">{trend.missing_analysis}</span>
            </li>
          </ul>

          <AiNote />

          <MoodTrendChart points={points} days={days} />

          {view.data && view.data.details.length > 0 ? (
            <>
              <SymptomMultiples details={view.data.details} />
              <EmotionBars details={view.data.details} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Symptom and emotion charts need individual records; none were readable in this range.
            </p>
          )}

          <CheckinTimeline patientId={id} points={points} />

          {points.length > DETAIL_LIMIT ? (
            <p className="text-xs text-muted-foreground">
              Symptom and emotion charts cover the {DETAIL_LIMIT} most recent records in this range,
              not all {points.length}.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function RangeSwitcher({ days, onChange }: { days: Range; onChange: (value: Range) => void }) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Range of check-ins to show">
      {RANGES.map((range) => (
        <button
          key={range}
          type="button"
          aria-pressed={days === range}
          onClick={() => onChange(range)}
          className={
            days === range
              ? "min-h-11 rounded-lg border border-primary bg-primary/10 px-4 text-sm font-medium text-primary"
              : "min-h-11 rounded-lg border border-border bg-card px-4 text-sm text-muted-foreground hover:bg-muted"
          }
        >
          {range} days
        </button>
      ))}
    </div>
  );
}
