"use client";

import { useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTableToggle } from "@/components/charts/chart-table-toggle";
import { DataTable } from "@/components/charts/data-table";
import { formatDateOnly } from "@/lib/utils";
import { SYMPTOM_KEYS, type CheckinDetail, type SymptomKey } from "@/types/api";

const LABELS: Record<SymptomKey, string> = {
  sleep: "Sleep",
  appetite: "Appetite",
  energy: "Energy",
  anxiety: "Anxiety",
  concentration: "Concentration",
  social_withdrawal: "Withdrawing socially",
  irritability: "Irritability",
};

/**
 * Small multiples, one per symptom, on the same 0–3 scale. Nulls stay as gaps: the backend gives
 * `null` when a check-in did not touch that symptom, and plotting it as 0 would read as "fine".
 *
 * The trend endpoint does not carry symptoms, so these come from the individual check-in details
 * fetched for the page — the most recent `DETAIL_LIMIT` of them.
 */
export function SymptomMultiples({ details }: { details: CheckinDetail[] }) {
  const [showTable, setShowTable] = useState(false);
  const chronological = [...details].reverse();
  const series = chronological.map((detail) => ({
    date: formatDateOnly(detail.created_at),
    values: detail.symptoms ?? {},
  }));

  const statsFor = (key: SymptomKey) => {
    const values = series
      .map((point) => point.values[key] ?? null)
      .filter((value): value is number => typeof value === "number");
    const last = [...series].reverse().find((point) => typeof point.values[key] === "number");
    return { values, last: last ? (last.values[key] as number) : null };
  };

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div className="space-y-1">
          <CardTitle>Symptoms</CardTitle>
          <p className="text-xs text-muted-foreground">
            0 = not raised · 1–3 = how much it came through · a gap means the check-in did not say.
            AI-generated, verify with the patient.
          </p>
        </div>
        <ChartTableToggle showTable={showTable} onChange={setShowTable} label="symptoms" />
      </CardHeader>
      <CardContent className="space-y-4">
        {showTable ? (
          <DataTable
            caption="Symptom scores per check-in, oldest first"
            columns={["Date", ...SYMPTOM_KEYS.map((key) => LABELS[key])]}
            rows={series.map((point) => [
              point.date,
              ...SYMPTOM_KEYS.map((key) => point.values[key] ?? null),
            ])}
          />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {SYMPTOM_KEYS.map((key) => {
              const { values, last } = statsFor(key);
              const average =
                values.length > 0
                  ? (values.reduce((total, value) => total + value, 0) / values.length).toFixed(1)
                  : null;
              const summary =
                values.length === 0
                  ? `${LABELS[key]} was not mentioned in this range.`
                  : `${LABELS[key]} came up in ${values.length} of ${series.length} check-ins, averaging ${average} of 3, most recently ${last}.`;

              return (
                <li key={key} className="space-y-1">
                  <p className="text-xs font-medium">{LABELS[key]}</p>
                  <div role="img" aria-label={summary} className="h-20 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={series.map((point) => ({ date: point.date, value: point.values[key] ?? null }))}
                        margin={{ top: 4, right: 4, bottom: 0, left: -32 }}
                      >
                        <XAxis dataKey="date" hide />
                        <YAxis domain={[0, 3]} tickCount={4} hide />
                        <Tooltip formatter={(value: unknown) => [value === null ? "not said" : `${value}/3`, LABELS[key]]} />
                        <Line
                          type="stepAfter"
                          dataKey="value"
                          stroke="var(--primary)"
                          strokeWidth={1.5}
                          dot={{ r: 2 }}
                          connectNulls={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-xs text-muted-foreground">{summary}</p>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
