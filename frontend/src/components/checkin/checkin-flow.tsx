"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api, shouldTypeInstead } from "@/lib/api";
import { PATIENT_LANDING } from "@/lib/auth/session-provider";
import type { CheckinResult as CheckinResponse } from "@/types/api";
import { CheckinResult } from "@/components/checkin/checkin-result";
import { Recorder } from "@/components/checkin/recorder";
import { TranscriptReview } from "@/components/checkin/transcript-review";
import { TypedNote } from "@/components/checkin/typed-note";

type Step = "record" | "review" | "result";
type Mode = "voice" | "typed";

const STEPS: { id: Step; label: string }[] = [
  { id: "record", label: "Record" },
  { id: "review", label: "Read it back" },
  { id: "result", label: "Done" },
];

/**
 * The three-step check-in: record, review, result. Audio lives in a ref and is dropped the moment
 * the flow finishes or restarts — it is never written to storage, and no object URL is ever made
 * for it. A submission in flight blocks repeat presses, because the backend has no idempotency key
 * and a second press would store a second check-in.
 */
export function CheckinFlow() {
  const router = useRouter();
  const audioRef = useRef<Blob | null>(null);

  const [step, setStep] = useState<Step>("record");
  const [mode, setMode] = useState<Mode>("voice");
  const [transcribing, setTranscribing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [note, setNote] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [result, setResult] = useState<CheckinResponse | null>(null);

  const reset = useCallback(() => {
    audioRef.current = null;
    setStep("record");
    setMode("voice");
    setTranscribing(false);
    setTranscript("");
    setNote("");
    setSeconds(0);
    setReviewError(null);
    setSubmitError(null);
    setSubmitting(false);
    setFallbackReason(null);
    setResult(null);
  }, []);

  const finish = useCallback(() => {
    reset();
    router.replace(PATIENT_LANDING);
  }, [reset, router]);

  const toTyped = useCallback((reason: string, keepText?: string) => {
    audioRef.current = null;
    setMode("typed");
    setStep("record");
    setTranscribing(false);
    setReviewError(null);
    setSubmitError(null);
    setFallbackReason(reason);
    if (keepText) setNote(keepText);
  }, []);

  /** Step 1 → 2: the recording is transcribed straight away, then shown for approval. */
  const handleRecording = useCallback(
    async (blob: Blob, recordedSeconds: number) => {
      audioRef.current = blob;
      setSeconds(recordedSeconds);
      setMode("voice");
      setStep("review");
      setTranscribing(true);
      setReviewError(null);
      setSubmitError(null);
      setTranscript("");

      try {
        const data = await api.transcribe(blob);
        setSeconds(Math.round(data.duration_seconds) || recordedSeconds);
        setTranscript(data.transcript);
      } catch (error) {
        if (error instanceof ApiError && error.code === "consent_required") {
          router.replace("/consent");
          return;
        }
        const message =
          error instanceof ApiError
            ? error.message
            : "We could not turn that into words. You can type what you meant below.";
        setReviewError(`${message} Edit the box below and submit that instead.`);
      } finally {
        setTranscribing(false);
      }
    },
    [router],
  );

  const submit = useCallback(async () => {
    if (submitting) return;
    const text = (mode === "voice" ? transcript : note).trim();
    if (!text) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      const payload =
        mode === "voice"
          ? await api.createCheckin({ transcript: text, duration_seconds: seconds })
          : await api.createCheckin({ note: text });
      setResult(payload);
      setStep("result");
    } catch (error) {
      if (shouldTypeInstead(error)) {
        // The voice path failed upstream; keep the person's words and let them send text.
        toTyped(
          error instanceof ApiError
            ? error.message
            : "We could not process that as a voice check-in.",
          text,
        );
      } else if (error instanceof ApiError && error.code === "consent_required") {
        router.replace("/consent");
      } else {
        setSubmitError(
          error instanceof ApiError
            ? `${error.message} Your check-in was not sent — press Submit to try again.`
            : "We could not reach Psylink. Check your connection and press Submit again.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }, [mode, note, router, seconds, submitting, toTyped, transcript]);

  return (
    <div className="space-y-4">
      <StepBar current={step} mode={mode} />

      {step === "record" && mode === "voice" ? (
        <Recorder
          onRecording={(blob, recordedSeconds) => void handleRecording(blob, recordedSeconds)}
          onTypeInstead={() =>
            toTyped("Type your check-in instead. Recording stays available if you change your mind.")
          }
        />
      ) : null}

      {step === "record" && mode === "typed" ? (
        <TypedNote
          value={note}
          onChange={setNote}
          onSubmit={() => void submit()}
          submitting={submitting}
          error={submitError}
          reason={fallbackReason}
          onBackToRecording={
            fallbackReason
              ? () => {
                  setMode("voice");
                  setStep("record");
                  setFallbackReason(null);
                  setSubmitError(null);
                }
              : undefined
          }
        />
      ) : null}

      {step === "review" ? (
        <TranscriptReview
          transcribing={transcribing}
          transcript={transcript}
          onTranscriptChange={setTranscript}
          error={reviewError}
          submitting={submitting}
          submitError={submitError}
          onReRecord={() => {
            audioRef.current = null;
            setStep("record");
            setMode("voice");
            setTranscript("");
            setReviewError(null);
            setSubmitError(null);
          }}
          onSubmit={() => void submit()}
        />
      ) : null}

      {step === "result" && result ? (
        <CheckinResult
          summary={result.analysis?.summary ?? null}
          mood={result.analysis?.mood_score ?? null}
          emotions={result.analysis?.emotions ?? []}
          analysisFailed={result.status === "analysis_failed" || result.analysis === null}
          showCrisis={result.show_crisis_resources}
          onDone={finish}
        />
      ) : null}
    </div>
  );
}

function StepBar({ current, mode }: { current: Step; mode: Mode }) {
  return (
    <ol className="flex items-center gap-2 text-xs text-muted-foreground">
      {STEPS.map((entry, index) => {
        const active = entry.id === current;
        const passed = STEPS.findIndex((s) => s.id === current) > index;
        const label =
          entry.id === "record" && mode === "typed" ? "Write" : entry.id === "result" ? "Result" : entry.label;
        return (
          <li key={entry.id} className="flex items-center gap-2">
            <span
              aria-current={active ? "step" : undefined}
              className={
                active
                  ? "rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground"
                  : "rounded-full border border-border px-3 py-1"
              }
            >
              {index + 1}. {label}
            </span>
            {passed && index < STEPS.length - 1 ? <span aria-hidden>·</span> : null}
          </li>
        );
      })}
    </ol>
  );
}
