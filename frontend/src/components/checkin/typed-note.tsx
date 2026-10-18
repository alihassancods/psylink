"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MAX_TEXT_CHARS } from "@/lib/api";

/**
 * The typed path. It is a first-class route through the flow, not an error state: no microphone,
 * a denied permission, a refused transcription and a failed submission all land here.
 */
export function TypedNote({
  value,
  onChange,
  onSubmit,
  submitting,
  error,
  onBackToRecording,
  reason,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  error: string | null;
  onBackToRecording?: () => void;
  reason?: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Write your check-in</CardTitle>
        {reason ? (
          <p className="text-sm text-muted-foreground">{reason}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Write as much or as little as you like. Nothing is submitted until you press submit.
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="note">Your words</Label>
          <Textarea
            id="note"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            rows={9}
            maxLength={MAX_TEXT_CHARS}
            placeholder="Last night I slept about four hours…"
            aria-describedby={error ? "note-error" : "note-help"}
          />
          <p id="note-help" className="text-xs text-muted-foreground">
            Sleep, the hardest part of today, who you have talked to — whatever feels relevant.
          </p>
        </div>

        {error ? (
          <p id="note-error" role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex flex-col gap-2 sm:flex-row">
          {onBackToRecording ? (
            <Button variant="outline" size="lg" className="sm:flex-1" onClick={onBackToRecording}>
              Use the microphone
            </Button>
          ) : null}
          <Button
            size="lg"
            className="sm:flex-1"
            onClick={onSubmit}
            disabled={submitting || value.trim().length === 0}
          >
            {submitting ? "Submitting…" : "Submit"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
