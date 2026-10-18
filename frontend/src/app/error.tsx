"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Next 16 passes `retry` alongside `error`, and `error` is `unknown` — narrowed here rather than
 * printed raw, because a server error's text can carry details a patient should never see.
 */
export default function AppError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  const known = error instanceof Error ? error.message : "";

  return (
    <main className="mx-auto w-full max-w-md p-6">
      <Card role="alert">
        <CardHeader>
          <CardTitle className="text-risk-high">This screen hit a problem</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            {known ||
              "Something went wrong while showing this page. Your check-ins are stored separately, so nothing you submitted is lost."}
          </p>
          <Button onClick={retry}>Try again</Button>
        </CardContent>
      </Card>
    </main>
  );
}
