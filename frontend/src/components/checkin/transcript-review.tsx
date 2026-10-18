"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { MAX_TEXT_CHARS } from "@/lib/api";

/**
 * Step 2. Nothing reaches the analyser unreviewed: the words are shown for approval and the person
 * can edit or delete any part of them before submitting.
 */
export function TranscriptReview({
  transcribing,
  transcript,
  onTranscriptChange,
  error,
  onReRecord,
  onSubmit,
  submitting,
  submitError,
}: {
  transcribing: boolean;
  transcript: string;
  onTranscriptChange: (value: string) => void;
  error: string | null;
  onReRecord: () => void;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{transcribing ? "Turning your voice into words…" : "Read it back"}</CardTitle>
        {!transcribing ? (
          <p className="text-sm text-muted-foreground">
            Fix anything that is wrong, or delete what you would rather not keep. Only what you
            submit is saved.
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {transcribing ? (
          <div role="status" aria-live="polite" className="space-y-2">
            <p className="text-sm text-muted-foreground">
              This usually takes a few seconds. Nothing has been saved yet.
            </p>
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : (
          <div className="space-y-2">
            <Label htmlFor="transcript">What you said</Label>
            <Textarea
              id="transcript"
              value={transcript}
              onChange={(event) => onTranscriptChange(event.target.value)}
              rows={8}
              maxLength={MAX_TEXT_CHARS}
              aria-describedby={error ? "review-error" : undefined}
            />
          </div>
        )}

        {error ? (
          <p id="review-error" role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {submitError ? (
          <p role="alert" className="text-sm text-destructive">
            {submitError}
          </p>
        ) : null}

        {!transcribing && transcript.trim().length > MAX_TEXT_CHARS - 500 ? (
          <p className="text-xs text-muted-foreground">
            {transcript.trim().length} of {MAX_TEXT_CHARS} characters.
          </p>
        ) : null}

        {!transcribing ? (
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="outline" size="lg" className="sm:flex-1" onClick={onReRecord}>
              Re-record
            </Button>
            <Button
              size="lg"
              className="sm:flex-1"
              onClick={onSubmit}
              disabled={submitting || transcript.trim().length === 0}
            >
              {submitting ? "Submitting…" : "Submit"}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
