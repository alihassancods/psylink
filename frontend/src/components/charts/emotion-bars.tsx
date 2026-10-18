"use client";

import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartTableToggle } from "@/components/charts/chart-table-toggle";
import { DataTable } from "@/components/charts/data-table";
import type { CheckinDetail } from "@/types/api";

/**
 * How often each emotion word appeared across the check-ins in view. Counts, not scores: the
 * backend returns up to five emotion labels per analysis and no intensity.
 */
export function EmotionBars({ details }: { details: CheckinDetail[] }) {
  const [showTable, setShowTable] = useState(false);

  const counts = new Map<string, number>();
  for (const detail of details) {
    for (const emotion of detail.emotions ?? []) {
      const key = emotion.toLowerCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  const data = [...counts.entries()]
    .map(([emotion, count]) => ({ emotion, count }))
    .sort((left, right) => right.count - left.count)
    .slice(0, 8);

  const summary =
    data.length === 0
      ? `No emotion words in these ${details.length} check-ins.`
      : `Across ${details.length} check-ins, the most frequent was “${data[0].emotion}” (${data[0].count}${
          data[0].count === 1 ? "" : " times"
        }), then ${data
          .slice(1, 4)
          .map((entry) => `“${entry.emotion}” (${entry.count})`)
          .join(", ")}.`;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <CardTitle>Emotions mentioned</CardTitle>
        <ChartTableToggle showTable={showTable} onChange={setShowTable} label="emotions" />
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{summary}</p>

        {showTable ? (
          <DataTable
            caption="Emotion words and how many check-ins mentioned each"
            columns={["Emotion", "Check-ins"]}
            rows={data.map((entry) => [entry.emotion, entry.count])}
          />
        ) : (
          <div role="img" aria-label={summary} className="w-full">
            <ResponsiveContainer
              width="100%"
              height={Math.max(80, data.length * 34)}
            >
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
              >
                <XAxis type="number" hide domain={[0, "dataMax"]} />
                <YAxis
                  type="category"
                  dataKey="emotion"
                  width={110}
                  tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                />
                <Tooltip formatter={(value: unknown) => [`${value}`, "check-ins"]} />
                <Bar dataKey="count" fill="var(--primary)" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {data.map((entry) => (
                    <Cell key={entry.emotion} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
