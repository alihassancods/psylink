import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Loading placeholders. `role="status"` + text so screen readers announce the wait. */

/**
 * Full-height placeholder for a region that has not resolved yet. It carries no max-width of its own
 * on purpose: it is sized by whatever column it sits in, so swapping it for real content does not
 * shift the layout — the old `max-w-md` made every skeleton narrower than the shell around it.
 */
export function PageLoading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex w-full flex-col gap-4", className)}
    >
      <p className="text-sm text-muted-foreground">{label}…</p>
      <Skeleton className="h-24 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-2/3 rounded-xl" />
    </div>
  );
}

export function CardListSkeleton({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)} role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, index) => (
        <Skeleton key={index} className="h-20 w-full rounded-xl" />
      ))}
    </div>
  );
}

/** Friendly failure with a retry. Never patient content in the message. */
export function ErrorPanel({
  title = "Something went wrong",
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <Card role="alert" className="border-risk-high-border bg-risk-high-surface">
      <CardHeader>
        <CardTitle className="text-risk-high">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm text-risk-high">
        <p>{message}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="min-h-11 rounded-lg border border-risk-high-border bg-card px-4 py-2 font-medium text-risk-high hover:bg-risk-high-surface"
          >
            {retryLabel}
          </button>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </CardHeader>
      {action ? <CardContent>{action}</CardContent> : null}
    </Card>
  );
}
