"use client";

import { cn } from "@/lib/utils";

/**
 * Every chart gets the same two views: a picture for shape and a table for exact numbers. The
 * toggle is a pair of real buttons with `aria-pressed`, so it survives without CSS and reads
 * correctly to a screen reader.
 */
export function ChartTableToggle({
  showTable,
  onChange,
  label,
  className,
}: {
  showTable: boolean;
  onChange: (showTable: boolean) => void;
  label: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-1", className)} role="group" aria-label={`View ${label}`}>
      <ToggleChip active={!showTable} onClick={() => onChange(false)}>
        Chart
      </ToggleChip>
      <ToggleChip active={showTable} onClick={() => onChange(true)}>
        Table
      </ToggleChip>
    </div>
  );
}

function ToggleChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "min-h-9 rounded-lg border px-2.5 text-xs font-medium",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-border bg-card text-muted-foreground hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}
