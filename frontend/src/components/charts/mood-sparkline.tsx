"use client";

import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";

import { cn } from "@/lib/utils";

interface MoodPoint {
  label: string;
  mood: number | null;
}

/**
 * Compact mood line for the patient home screen. Null moods are dropped so the line breaks rather
 * than dipping to zero — a missing check-in is not a mood of nothing.
 */
export function MoodSparkline({
  points,
  className,
  summary,
}: {
  points: MoodPoint[];
  className?: string;
  summary?: string;
}) {
  const filled = points.filter((point) => point.mood !== null);
  const text =
    summary ??
    (filled.length === 0
      ? "No mood scores yet."
      : `Mood over the last ${filled.length} check-ins, from ${Math.min(
          ...filled.map((point) => point.mood as number),
        )} to ${Math.max(...filled.map((point) => point.mood as number))} out of 10.`);

  return (
    <div className={cn("space-y-2", className)}>
      <div aria-hidden className={cn("h-20 w-full", className)}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <XAxis dataKey="label" hide />
            <YAxis domain={[1, 10]} hide />
            <Tooltip
              content={({ active, payload }) =>
                active && payload && payload.length ? (
                  <span className="rounded-md border border-border bg-card px-2 py-1 text-xs">
                    {String(payload[0]?.payload?.label ?? "")} mood {String(payload[0]?.value ?? "")}
                  </span>
                ) : null
              }
            />
            <Line
              type="monotone"
              dataKey="mood"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted-foreground">{text}</p>
    </div>
  );
}
