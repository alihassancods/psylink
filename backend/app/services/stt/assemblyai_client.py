"""AssemblyAI pre-recorded transcription, run off the event loop.

Three rules shape this file:

* The SDK is blocking, so every call it makes happens in a worker thread via
  ``asyncio.to_thread`` — never directly in an async route.
* Nothing is ever written to disk: the SDK accepts raw ``bytes``, so the upload is a
  memory buffer and there is no temp file to clean up or leak.
* The remote transcript is deleted on every path that obtained its id — success, error
  status, empty text, over-length, or a timeout while polling. Submission and the id are
  captured before polling starts precisely so the timeout path still has an id to delete.

Logging is limited to ids and status: no transcript text, no audio, no prompt.
"""

import asyncio
import logging
from dataclasses import dataclass

import assemblyai
from assemblyai import AssemblyAIError, Transcriber, Transcript, TranscriptStatus
from assemblyai.prerecorded.v2 import TranscriptionConfig
from assemblyai.types import TranscriptError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: How long the SDK may poll for a finished transcript.
POLL_TIMEOUT_SECONDS = 30.0
#: Outer guard: the SDK should end first; this only fires if a socket hangs.
OUTER_TIMEOUT_SECONDS = 34.0
#: Deletion must not become the reason a patient waits.
DELETE_TIMEOUT_SECONDS = 15.0


class STTError(Exception):
    """Base: transcription could not produce usable text."""


class STTRateLimited(STTError):
    """AssemblyAI answered 429."""


class STTTimeout(STTError):
    """Polling ran out of time."""


class STTUnavailable(STTError):
    """AssemblyAI is unreachable, refused the request, or is not configured."""


class STTFailed(STTError):
    """AssemblyAI accepted the job and reported an error against this specific clip."""


class AudioTooLong(STTError):
    """The recording is over the configured length, locally or as reported remotely."""


class EmptyTranscript(STTError):
    """Completed with no words in it (silence, or audio we cannot use)."""


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    duration_seconds: float


def _client_configured() -> Transcriber:
    """Build a transcriber and point the SDK's default client at the same key.

    ``Transcript.delete_by_id`` uses the global client, so both have to carry the key. It is
    read from settings on every call, which lets tests and rotations take effect at once.
    """
    api_key = get_settings().assemblyai_api_key
    if not api_key:
        raise STTUnavailable("ASSEMBLYAI_API_KEY is not configured")
    assemblyai.settings.api_key = api_key
    return Transcriber(api_key=api_key)


def _too_long_hint(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in ("too long", "duration", "too large", "length"))


def _map_error(exc: AssemblyAIError) -> STTError:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return STTRateLimited("assemblyai rate limited")
    if status_code == 400 and _too_long_hint(str(exc)):
        return AudioTooLong("audio exceeds the permitted length")
    if isinstance(exc, TranscriptError):
        return STTTimeout("transcription did not finish in time")
    return STTUnavailable(f"assemblyai error (status {status_code})")


def _delete_safely(transcript_id: str) -> None:
    """Remove the transcript remotely. Failure is logged by id only, never by content."""
    try:
        Transcript.delete_by_id(transcript_id)
    except Exception as exc:  # deletion failure must not change the patient's answer
        logger.warning(
            "could not delete assemblyai transcript %s: %s", transcript_id, type(exc).__name__
        )


class _TranscriptHandle:
    """Holds the id as soon as submission succeeds, so `finally` can always delete."""

    def __init__(self) -> None:
        self.transcript_id: str | None = None


def _run_blocking(audio: bytes, language_code: str, handle: _TranscriptHandle) -> Transcript:
    """The blocking SDK work, executed in a worker thread."""
    transcriber = _client_configured()
    config = TranscriptionConfig(language_code=language_code)
    transcript = transcriber.submit(audio, config=config)
    handle.transcript_id = transcript.id
    transcript.wait_for_completion(poll_timeout=POLL_TIMEOUT_SECONDS)
    return transcript


async def transcribe_bytes(
    audio: bytes,
    *,
    language_code: str = "en",
    max_seconds: int | None = None,
) -> TranscriptionResult:
    """Transcribe an in-memory audio clip and delete the remote transcript afterwards.

    Args:
        audio: The raw upload bytes. Never written to disk and never logged.
        language_code: Fixed language for the request; English by default.
        max_seconds: Rejects a result whose reported duration exceeds this. ``None`` means
            the caller enforces length elsewhere.

    Raises:
        STTRateLimited, STTTimeout, STTUnavailable, AudioTooLong, EmptyTranscript.
    """
    handle = _TranscriptHandle()
    try:
        try:
            transcript = await asyncio.wait_for(
                asyncio.to_thread(_run_blocking, audio, language_code, handle),
                timeout=OUTER_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise STTTimeout("transcription exceeded the request budget") from exc
        except AssemblyAIError as exc:
            raise _map_error(exc) from exc

        if transcript.status == TranscriptStatus.error:
            reason = str(getattr(transcript, "error", "") or "")
            if _too_long_hint(reason):
                raise AudioTooLong("audio exceeds the permitted length")
            # The job was accepted and failed on this clip: distinct from the service being
            # down, because retrying the same audio would not help.
            raise STTFailed("transcription failed at assemblyai")

        duration = getattr(transcript, "audio_duration", None)
        text = (getattr(transcript, "text", None) or "").strip()

        if (
            max_seconds is not None
            and isinstance(duration, (int, float))
            and duration > max_seconds
        ):
            # Checked before emptiness: "too long" is the more actionable answer for the UI.
            raise AudioTooLong(f"audio is longer than {max_seconds} seconds")

        if not text:
            raise EmptyTranscript("no speech was detected")

        return TranscriptionResult(transcript=text, duration_seconds=float(duration or 0.0))
    finally:
        transcript_id = handle.transcript_id
        if transcript_id:
            # Best effort, bounded, and off the loop: the patient's request already has an
            # answer by the time this returns.
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(_delete_safely, transcript_id),
                    timeout=DELETE_TIMEOUT_SECONDS,
                )
            except TimeoutError, asyncio.CancelledError:
                logger.warning("timed out deleting assemblyai transcript %s", transcript_id)
