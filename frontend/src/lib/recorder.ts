/**
 * Microphone capability, kept out of the component so it can be tested without a DOM.
 * The backend accepts webm/opus, ogg, mp4, mpeg, wav, aac and flac; browsers do not all offer the
 * same three of those, so the picker asks MediaRecorder rather than guessing from the UA string.
 */

export const MAX_RECORD_SECONDS = 120;

const PREFERRED_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
  "audio/mpeg",
];

export function isMediaRecorderSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder === "function" &&
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

/** Null means "nothing this browser offers is something the backend accepts" → type instead. */
export function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return null;
  }
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function isMicrophoneBlocked(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name ?? "";
  return name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError";
}

export function isMicrophoneMissing(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name ?? "";
  return name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError";
}

export function microphoneErrorMessage(error: unknown): string {
  if (isMicrophoneBlocked(error)) {
    return "The microphone is blocked for this site. You can allow it in your browser's site settings, or type your check-in instead.";
  }
  if (isMicrophoneMissing(error)) {
    return "No microphone was found. You can type your check-in instead.";
  }
  return "Your microphone did not start. Try again, or type your check-in instead.";
}

export function formatClock(totalSeconds: number) {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
