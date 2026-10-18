"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { formatRelativeDay } from "@/lib/utils";
import { asState, useCheckinsQuery } from "@/lib/queries";

/**
 * Patient home. One primary action: start a check-in.
 *
 * Cut with a note: the spec also asks for a small mood trend here. `GET /api/checkins` returns
 * `summary` and `risk` but no mood score, so a mood line would need inventing or caching in the
 * browser; the trend chart ships on the clinician side, where `/trend` does return `mood_score`.
 * Raw risk labels stay off patient screens by design.
 */
export function HomeView() {
  const checkins = asState(useCheckinsQuery(4));
  const items = checkins.data?.items ?? [];
  const latest = items[0];

  return (
    <div className="space-y-6">
      <Card className="bg-primary text-primary-foreground">
        <CardContent className="space-y-4 p-6">
          <h1 className="text-xl font-semibold text-balance">How have you been since we last spoke?</h1>
          <p className="text-sm text-primary-foreground">
            About two minutes. You read the words before anything is submitted, and you can change
            them.
          </p>
          <Button size="lg" variant="secondary" className="w-full bg-card text-primary" asChild>
            <Link href="/checkin">Start check-in</Link>
          </Button>
        </CardContent>
      </Card>

      <section aria-labelledby="latest-heading" className="space-y-3">
        <h2 id="latest-heading" className="text-sm font-semibold">
          Last check-in
        </h2>

        {checkins.status === "loading" ? <CardListSkeleton count={1} /> : null}
        {checkins.status === "error" ? (
          <ErrorPanel
            title="We could not load your check-ins"
            message={checkins.message}
            onRetry={() => void checkins.reload()}
          />
        ) : null}
        {checkins.status === "success" && !latest ? (
          <EmptyState
            title="No check-ins yet"
            description="Your first one takes about two minutes. It stays private to your care team."
          />
        ) : null}
        {latest ? (
          <Card>
            <CardHeader className="pb-1">
              <CardTitle className="text-sm font-medium">{formatRelativeDay(latest.created_at)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {latest.summary ?? "We could not summarise this one — it shows as you wrote it."}
              </p>
              <Button variant="outline" size="sm" asChild>
                <Link href="/history">See your history</Link>
              </Button>
            </CardContent>
          </Card>
        ) : null}
      </section>

      <nav aria-label="Patient sections" className="grid gap-2 sm:grid-cols-2">
        <Button variant="outline" size="lg" asChild>
          <Link href="/history">History</Link>
        </Button>
        <Button variant="outline" size="lg" asChild>
          <Link href="/settings">Privacy and sharing</Link>
        </Button>
      </nav>
    </div>
  );
}
