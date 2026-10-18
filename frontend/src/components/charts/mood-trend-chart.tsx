"use client";

import { useState } from "react";
import {
  CartesianGrid,
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
import type { TrendPoint } from "@/types/api";

/**
 * Mood over time. Null moods stay as gaps instead of becoming zero: a check-in whose analysis
 * failed is missing information, not a mood of nothing. The API returns points newest-first, so
 * they are reversed here for a left-to-right reading.
 */
export function MoodTrendChart({ points, days }: { points: TrendPoint[]; days: number }) {
  const [showTable, setShowTable] = useState(false);
  const chronological = [...points].reverse();
  const values = chronological
    .map((point) => point.mood_score)
    .filter((value): value is number => value !== null);

  const summary =
    values.length === 0
      ? `No mood scores in the last ${days} days.`
      : values.length === 1
        ? `One mood score in the last ${days} days: ${values[0]} out of 10.`
        : `Mood over the last ${days} days ran ${Math.min(...values)} to ${Math.max(
            ...values,
          )} out of 10 across ${values.length} scored check-ins. It opened at ${
            values[0]
          } and ended at ${values[values.length - 1]}. ${
            chronological.length - values.length
          } check-in(s) had no mood score.`;

  const data = chronological.map((point) => ({
    date: formatDateOnly(point.created_at),
    mood: point.mood_score,
  }));

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 sm:flex-row">
        <CardTitle>Mood</CardTitle>
        <ChartTableToggle showTable={showTable} onChange={setShowTable} label="mood" />
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{summary}</p>

        {showTable ? (
          <DataTable
            caption={`Mood scores for the last ${days} days, oldest first`}
            columns={["Date", "Mood out of 10"]}
            rows={data.map((row) => [row.date, row.mood])}
          />
        ) : (
          <div role="img" aria-label={summary} className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} minTickGap={24} />
                <YAxis domain={[1, 10]} tickCount={5} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                <Tooltip
                  formatter={(value: unknown) => [
                    value === null || value === undefined ? "no score" : `${value}/10`,
                    "Mood",
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="mood"
                  stroke="var(--primary)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
