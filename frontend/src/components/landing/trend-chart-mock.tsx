import { heroVisual } from "@/app/(landing)/content";

/**
 * A drawn mood trend, not a chart library. `recharts` is roughly a third of a megabyte and belongs
 * on the signed-in screens; shipping it here would put the heaviest module in the app on the page
 * that has to load fastest, for a picture that carries no real data.
 *
 * The points are hand-written and synthetic, which is also why the caption says so.
 */
export function TrendChartMock() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-foreground">{heroVisual.trend.label}</p>
        <p className="text-xs text-muted-foreground">{heroVisual.trend.caption}</p>
      </div>

      <p className="sr-only">{heroVisual.trend.srOnly}</p>

      <svg
        aria-hidden="true"
        viewBox="0 0 280 120"
        className="mt-4 h-32 w-full"
        fill="none"
        preserveAspectRatio="none"
      >
        {/* Gridlines */}
        <line x1="0" y1="20" x2="280" y2="20" stroke="var(--border)" strokeWidth="1" />
        <line x1="0" y1="65" x2="280" y2="65" stroke="var(--border)" strokeWidth="1" />
        <line x1="0" y1="110" x2="280" y2="110" stroke="var(--border)" strokeWidth="1" />

        {/* Area under the line, so the dip reads as shape before it reads as numbers. */}
        <polygon points={`10,110 ${POINTS} 270,110`} fill="var(--accent)" opacity="0.10" />

        <polyline
          points={POINTS}
          stroke="var(--accent)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* The lowest day, marked the way the app marks a flagged moment — quietly. */}
        <circle cx="130" cy="81.5" r="4" fill="var(--card)" stroke="var(--accent)" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

/** Fourteen synthetic days: steady, a midweek dip, then a recovery. */
const POINTS = [
  [10, 48],
  [30, 53],
  [50, 58],
  [70, 62],
  [90, 67],
  [110, 77],
  [130, 81.5],
  [150, 77],
  [170, 72],
  [190, 67],
  [210, 58],
  [230, 53],
  [250, 48],
  [270, 44],
]
  .map(([x, y]) => `${x},${y}`)
  .join(" ");
