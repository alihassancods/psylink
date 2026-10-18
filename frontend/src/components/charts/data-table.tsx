import { cn } from "@/lib/utils";

/** The textual twin of a chart. Real `<table>` semantics, so numbers are copyable and announced. */
export function DataTable({
  caption,
  columns,
  rows,
  className,
}: {
  caption: string;
  columns: string[];
  rows: (string | number | null)[][];
  className?: string;
}) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className="border-b border-border py-2 pr-3 text-left font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className={cn(
                    "border-b border-border py-2 pr-3",
                    cellIndex === 0 ? "font-medium" : "text-muted-foreground",
                  )}
                >
                  {cell === null || cell === "" ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="py-3 text-muted-foreground">
                Nothing in this range.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
