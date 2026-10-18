"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { MicIcon, MicOffIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  MAX_RECORD_SECONDS,
  formatClock,
  isMediaRecorderSupported,
  microphoneErrorMessage,
  pickMimeType,
} from "@/lib/recorder";

const PROMPTS = [
  "How was your sleep?",
  "What was hardest today?",
  "Who have you talked to this week?",
  "What helped, even a little?",
];

/**
 * Step 1 of a check-in. The permission explainer always comes before the browser prompt, and every
 * path that does not produce a recording ends in the typed fallback rather than a dead end.
 *
 * The audio Blob is handed straight to the review step and never written down: no object URL, no
 * storage, no console output. Tracks and timers are released on stop, on unmount, and on navigation
 * (cache components keep a route mounted when you leave it, so the recorder would otherwise sit
 * recording in the background).
 */
export function Recorder({
  onRecording,
  onTypeInstead,
}: {
  onRecording: (audio: Blob, seconds: number) => void;
  onTypeInstead: () => void;
}) {
  const pathname = usePathname();
  const supported = isMediaRecorderSupported() && pickMimeType() !== null;

  const [phase, setPhase] = useState<"explain" | "ready" | "recording">(supported ? "explain" : "ready");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(
    supported ? null : "This browser cannot record audio, so type your check-in instead.",
  );
  const [prompt, setPrompt] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const elapsedRef = useRef(0);
  const discardRef = useRef(false);

  const release = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  /** Abandons whatever is in flight; used when the person leaves the page mid-recording. */
  const abandon = useCallback(() => {
    discardRef.current = true;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorderRef.current = null;
    release();
  }, [release]);

  useEffect(() => {
    return () => abandon();
  }, [abandon]);

  // A pathname change means the person navigated away while the route stayed mounted, so the
  // in-flight recording is dropped. The UI reset happens in `onstop`, never in this effect body.
  const lastPathnameRef = useRef(pathname);
  useEffect(() => {
    if (lastPathnameRef.current === pathname) return;
    lastPathnameRef.current = pathname;
    abandon();
  }, [abandon, pathname]);

  async function askForMicrophone() {
    setError(null);
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      setPhase("ready");
    } catch (cause) {
      setError(microphoneErrorMessage(cause));
    }
  }

  function stopTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function start() {
    const stream = streamRef.current;
    const mimeType = pickMimeType();
    if (!stream || !mimeType) {
      setError("The microphone is not ready. Type your check-in instead, or try again.");
      return;
    }

    const recorder = new MediaRecorder(stream, { mimeType });
    chunksRef.current = [];
    discardRef.current = false;
    elapsedRef.current = 0;
    setSeconds(0);

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType });
      const discarded = discardRef.current;
      discardRef.current = false;
      stopTimer();
      release();
      recorderRef.current = null;
      if (!discarded && blob.size > 0) {
        onRecording(blob, elapsedRef.current);
        return;
      }
      setPhase(supported ? "explain" : "ready");
      setSeconds(0);
    };

    recorderRef.current = recorder;
    recorder.start();
    setPhase("recording");

    timerRef.current = window.setInterval(() => {
      elapsedRef.current += 1;
      setSeconds(elapsedRef.current);
      // Hard cap: the backend rejects longer audio, so stop before it can.
      if (elapsedRef.current >= MAX_RECORD_SECONDS) {
        recorderRef.current?.stop();
      }
    }, 1000);
  }

  function stop() {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  }

  function cancel() {
    discardRef.current = true;
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    stopTimer();
    release();
    setSeconds(0);
    setPhase("ready");
  }

  const remaining = Math.max(0, MAX_RECORD_SECONDS - seconds);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{phase === "recording" ? "Recording" : "Speak for about two minutes"}</CardTitle>
        {phase !== "recording" ? (
          <p className="text-sm text-muted-foreground">
            Say whatever is on your mind. When you stop, you will read the words before anything is
            submitted.
          </p>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-5">
        <PromptChips prompts={PROMPTS} active={prompt} onPick={setPrompt} />

        {phase === "explain" ? (
          <div className="space-y-3 rounded-lg border border-border bg-muted p-4">
            <p className="text-sm">
              <span className="font-medium">Your browser will ask to use the microphone.</span>{" "}
              Psylink only uses it while you are recording: your voice goes to a speech-to-text
              service, and it is not stored here afterwards.
            </p>
            <Button size="lg" onClick={() => void askForMicrophone()}>
              <MicIcon className="size-5" aria-hidden />
              Allow microphone
            </Button>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {phase === "ready" ? (
          <div className="space-y-3">
            <Button size="lg" className="w-full" onClick={start} disabled={!supported}>
              <MicIcon className="size-5" aria-hidden />
              Start recording
            </Button>
            <Button size="lg" variant="outline" className="w-full" onClick={onTypeInstead}>
              <MicOffIcon className="size-5" aria-hidden />
              Type instead
            </Button>
            {!supported ? (
              <p className="text-xs text-muted-foreground">
                Recording is not available in this browser, so typing is the way in.
              </p>
            ) : null}
          </div>
        ) : null}

        {phase === "recording" ? (
          <div className="space-y-4 text-center">
            <div className="relative mx-auto flex size-24 items-center justify-center">
              <span
                aria-hidden
                className="psylink-pulse absolute inset-0 rounded-full bg-destructive/30"
              />
              <span className="relative flex size-16 items-center justify-center rounded-full bg-destructive text-white">
                <MicIcon className="size-7" aria-hidden />
              </span>
            </div>
            <p>
              <span className="font-mono text-2xl tabular-nums">{formatClock(seconds)}</span>{" "}
              <span className="text-sm text-muted-foreground">
                of {formatClock(MAX_RECORD_SECONDS)} · {remaining}s left
              </span>
            </p>
            <p className="sr-only" aria-live="polite">
              Recording {formatClock(seconds)}. Stops by itself at {formatClock(MAX_RECORD_SECONDS)}.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button size="lg" variant="outline" className="flex-1" onClick={cancel}>
                Discard
              </Button>
              <Button size="lg" className="flex-1" onClick={stop}>
                Stop and read it back
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Talking points, not a form. Picking one reminds the person what they meant to say. */
function PromptChips({
  prompts,
  active,
  onPick,
}: {
  prompts: string[];
  active: string | null;
  onPick: (prompt: string | null) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">If it helps to start somewhere</p>
      <div className="flex flex-wrap gap-2">
        {prompts.map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={active === item}
            onClick={() => onPick(active === item ? null : item)}
            className="min-h-11 rounded-full border border-border bg-card px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {item}
          </button>
        ))}
      </div>
      {active ? (
        <p className="text-sm text-foreground">
          Start with: <span className="font-medium">{active}</span>
        </p>
      ) : null}
    </div>
  );
}
