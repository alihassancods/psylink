"use client";

import { use, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { AiNote } from "@/components/clinician/ai-note";
import { CheckinTimeline } from "@/components/clinician/checkin-timeline";
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { useCheckinDetails, usePatientsQuery, useTrendQuery } from "@/lib/queries";
import type { TrendPoint } from "@/types/api";

const RANGES = [7, 14, 30] as const;
type Range = (typeof RANGES)[number];

/**
 * Trend requests carry mood, risk and summary only. Symptoms and emotions live on the individual
 * analysis, so the most recent records are read to build those charts. Capped at 20, and the page
 * says so rather than implying the chart covers the whole range. Each record is now its own cached
 * query, so the cost is one request per record *not already seen* — switching the range re-fetches
 * the trend alone, and revisiting a patient fetches nothing.
 */
const DETAIL_LIMIT = 20;

/** Shared empty array so the detail keys below are not rebuilt on every render. */
const NO_POINTS: TrendPoint[] = [];

/**
 * recharts plus its d3 tree is the heaviest code in this route and the last thing a clinician reads.
 * Loaded on demand so the counts, the timeline and the patient's name render without waiting on a
 * charting library. `ssr: false` is valid because this module is already a Client Component —
 * `next/dist/docs/01-app/02-guides/lazy-loading.md`.
 */
const MoodTrendChart = dynamic(
  () => import("@/components/charts/mood-trend-chart").then((module) => module.MoodTrendChart),
  { ssr: false, loading: () => <CardListSkeleton count={1} /> },
);
const SymptomMultiples = dynamic(
  () => import("@/components/charts/symptom-multiples").then((module) => module.SymptomMultiples),
  { ssr: false, loading: () => <CardListSkeleton count={2} /> },
);
const EmotionBars = dynamic(
  () => import("@/components/charts/emotion-bars").then((module) => module.EmotionBars),
  { ssr: false, loading: () => <CardListSkeleton count={1} /> },
);

export function PatientDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [days, setDays] = useState<Range>(14);

  const trendView = useTrendQuery(id, days);
  const roster = usePatientsQuery();
  // The list page already filled this cache entry. It used to be re-pulled — 100 rows — to read one
  // display name.
  const name =
    roster.data?.items.find((patient) => patient.patient_id === id)?.display_name ?? null;

  const trend = trendView.data;
  const points = trend?.points ?? NO_POINTS;

  const detailIds = useMemo(
    () => points.slice(0, DETAIL_LIMIT).map((point) => point.checkin_id),
    [points],
  );
  const details = useCheckinDetails(id, detailIds);

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <Link
          className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
          href="/patients"
        >
          All patients
        </Link>
        <h1 className="text-lg font-semibold">{name ?? "This patient"}</h1>
        <p className="text-sm text-muted-foreground">
          Only what this patient chose to share, and only while their consent is active.
        </p>
      </div>

      <RangeSwitcher days={days} onChange={setDays} />

      {trendView.isPending ? <CardListSkeleton count={3} /> : null}

      {trendView.isError ? (
        <ErrorPanel
          title="This patient is not available"
          message={`${
            trendView.error instanceof Error && trendView.error.message
              ? trendView.error.message
              : "We could not load this patient."
          } If they revoked consent, their history closes immediately.`}
          onRetry={() => void trendView.refetch()}
        />
      ) : null}

      {trend && points.length === 0 ? (
        <EmptyState
          title="No check-ins in this range"
          description="Nothing was shared in the last few days. Widen the range, or check back after the next check-in."
        />
      ) : null}

      {trend && points.length > 0 ? (
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

          {details.length > 0 ? (
            <>
              <SymptomMultiples details={details} />
              <EmotionBars details={details} />
            </>
          ) : detailIds.length > 0 ? (
            <CardListSkeleton count={2} />
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
