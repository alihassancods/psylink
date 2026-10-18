"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CrisisCard } from "@/components/crisis/crisis-card";

/**
 * Step 3. Deliberately free of risk labels, red, or anything that reads as a diagnosis: the
 * summary describes what the person said, and the crisis card appears exactly when the API asks for
 * it — including when analysis failed, because "we could not tell" must not look like "all fine".
 */
export function CheckinResult({
  summary,
  mood,
  emotions,
  analysisFailed,
  showCrisis,
  onDone,
}: {
  summary: string | null;
  mood: number | null;
  emotions: string[];
  analysisFailed: boolean;
  showCrisis: boolean;
  onDone: () => void;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Thank you for checking in</CardTitle>
          <p className="text-sm text-muted-foreground">
            This is saved, and only your care team can read it.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {analysisFailed ? (
            <p className="text-sm">
              We could not put this into words just now. What you said is still saved, and your
              psychologist or psychiatrist will see it as you wrote it.
            </p>
          ) : (
            <>
              {summary ? (
                <p className="text-lg leading-relaxed">{summary}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  We did not get a summary back for this one.
                </p>
              )}

              {mood !== null ? (
                <p className="text-sm text-muted-foreground">
                  The way you described things came through at {mood} out of 10.
                </p>
              ) : null}

              {emotions.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">You mentioned feeling</p>
                  <ul className="flex flex-wrap gap-2">
                    {emotions.map((emotion) => (
                      <li
                        key={emotion}
                        className="rounded-full border border-border bg-muted px-3 py-1 text-sm"
                      >
                        {emotion}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}

          <Button size="lg" className="w-full" onClick={onDone}>
            Done
          </Button>
        </CardContent>
      </Card>

      {showCrisis ? <CrisisCard /> : null}
    </div>
  );
}
