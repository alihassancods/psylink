"""``POST /api/transcribe`` — patient-only speech-to-text for the check-in recorder.

The browser records with MediaRecorder and posts the clip here; the returned text goes into
an editable box, and only what the patient approves is ever sent to ``/api/checkins``. The
audio itself is not stored, not written to disk, and not logged anywhere.

Two upload shapes are accepted, because the recorder posts a raw blob while a hand-written
``FormData`` post arrives as multipart:

* ``audio/webm`` (and friends) — the body *is* the audio.
* ``multipart/form-data`` — the first part with a filename or an audio type is used.

Both read the body through a size-capped stream and parse it in memory. Starlette's own form
parser is deliberately not used: it spools parts beyond ~1 MB into a temporary file, and
putting the patient's audio on disk is exactly what this endpoint promises not to do.

Refusals use the standard shape from :mod:`app.api.errors`:

======  ==========================  =========================================
Status  Code                        Meaning
======  ==========================  =========================================
400     ``unsupported_audio``       Content type the recorder should not send.
400     ``empty_audio``             No bytes in the body, or no file part.
400     ``audio_too_long``          Recording longer than ``MAX_AUDIO_SECONDS``.
403     ``consent_required``        Patient has no active consent on file.
413     ``audio_too_large``         Body above ``MAX_AUDIO_MB``.
429     ``rate_limited``            Per-patient hourly cap reached.
502     ``empty_transcript``        Speech-to-text succeeded with no words.
502     ``stt_failed``              AssemblyAI reported an error for this clip.
503     ``stt_unavailable``         AssemblyAI unreachable, refused, or misconfigured.
504     ``stt_timeout``             Speech-to-text ran past its budget.
======  ==========================  =========================================

Every one of those is a "type it instead" path in the frontend, which is the point: the
recorder is a convenience, never a dependency.
"""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.consent import has_active_consent
from app.api.errors import api_error
from app.core.config import get_settings
from app.core.deps import CurrentUser, require_role
from app.core.ratelimit import transcribe_limiter
from app.services.stt.assemblyai_client import (
    AudioTooLong,
    EmptyTranscript,
    STTFailed,
    STTRateLimited,
    STTTimeout,
    STTUnavailable,
    transcribe_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transcribe", tags=["speech-to-text"])

#: What MediaRecorder and iOS Safari actually emit. Parameters are stripped before the
#: comparison, so ``audio/webm;codecs=opus`` matches ``audio/webm``.
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "audio/webm",
        "audio/ogg",
        "application/ogg",
        "audio/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/aac",
        "audio/flac",
        "multipart/form-data",  # a wrapper around one of the types above
    }
)

#: Content types a browser has been observed using for a MediaRecorder blob.
_HEADER_END = b"\r\n\r\n"
_BOUNDARY_IN_HEADER = re.compile(r'boundary=("?)([^";]+)\1', re.IGNORECASE)


class TranscribeResponse(BaseModel):
    """The editable text plus the clip length, for the check-in form."""

    transcript: str
    duration_seconds: float


def _media_type(request: Request) -> str:
    """The media type alone, parameters (``;codecs=opus``) stripped and lowercased."""
    return (request.headers.get("content-type") or "").split(";")[0].strip().lower()


def _multipart_boundary(request: Request) -> bytes | None:
    """The multipart boundary, unquoted when the client quoted it."""
    match = _BOUNDARY_IN_HEADER.search(request.headers.get("content-type") or "")
    return match.group(2).encode() if match else None


def _audio_from_multipart(body: bytes, boundary: bytes) -> bytes:
    """Pull the first file part out of a multipart body, in memory only.

    Intentionally narrow: this endpoint takes one audio part, so anything it cannot read as
    one is refused instead of guessed at.
    """
    for segment in body.split(b"--" + boundary)[1:]:
        if segment.startswith(b"--"):  # the closing delimiter
            break
        head, separator, payload = segment.partition(_HEADER_END)
        if not separator:
            continue
        headers = head.lower()
        if b"filename" not in headers and b"content-type: audio" not in headers:
            continue
        return payload.removesuffix(b"\r\n")
    raise api_error("empty_audio", "the multipart body contained no audio file part")


async def _read_capped(request: Request, limit_bytes: int) -> bytes:
    """Stream the body into memory, refusing it the moment it exceeds ``limit_bytes``.

    Never ``await request.body()``: that buffers an arbitrary upload before the cap is
    noticed. Chunked reading rejects an oversized request after roughly one limit-sized
    read, whatever the client claimed in ``Content-Length``.
    """
    buffered = bytearray()
    async for chunk in request.stream():
        buffered.extend(chunk)
        if len(buffered) > limit_bytes:
            raise api_error(
                "audio_too_large",
                f"audio exceeds {limit_bytes // (1024 * 1024)} MB",
                status_code=413,
            )
    return bytes(buffered)


@router.post("", response_model=TranscribeResponse, status_code=200)
async def transcribe_audio(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> TranscribeResponse:
    """Transcribe one uploaded clip into editable text for the check-in form."""
    settings = get_settings()

    media_type = _media_type(request)
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise api_error(
            "unsupported_audio",
            f"unsupported content type {media_type or 'missing'}; "
            "expected audio/webm, audio/ogg, audio/mp4 or audio/wav",
        )

    limit_bytes = settings.max_audio_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit_bytes:
        # Early refusal from the header, before any of the body is read.
        raise api_error(
            "audio_too_large", f"audio exceeds {settings.max_audio_mb} MB", status_code=413
        )

    body = await _read_capped(request, limit_bytes)

    if media_type == "multipart/form-data":
        boundary = _multipart_boundary(request)
        if not boundary:
            raise api_error("unsupported_audio", "multipart upload without a boundary")
        audio = _audio_from_multipart(body, boundary)
    else:
        audio = body

    if not audio:
        raise api_error("empty_audio", "no audio bytes were uploaded")

    if not transcribe_limiter.check(str(user.id)):
        retry_after = transcribe_limiter.retry_after(str(user.id))
        logger.info("transcribe rate limited for a patient (retry in %ds)", retry_after)
        raise api_error(
            "rate_limited",
            f"transcription limit reached; try again in {retry_after} seconds",
            status_code=429,
        )

    if not await has_active_consent(user):
        raise api_error(
            "consent_required",
            "an active consent is required before audio can be transcribed",
            status_code=403,
        )

    try:
        result = await transcribe_bytes(audio, max_seconds=settings.max_audio_seconds)
    except STTRateLimited as exc:
        raise api_error("rate_limited", "transcription service is busy", status_code=429) from exc
    except STTTimeout as exc:
        raise api_error("stt_timeout", "transcription timed out", status_code=504) from exc
    except EmptyTranscript as exc:
        raise api_error("empty_transcript", "no speech was detected", status_code=502) from exc
    except STTFailed as exc:
        raise api_error(
            "stt_failed", "transcription failed for this recording", status_code=502
        ) from exc
    except AudioTooLong as exc:
        raise api_error(
            "audio_too_long", f"recording must be {settings.max_audio_seconds} seconds or less"
        ) from exc
    except STTUnavailable as exc:
        raise api_error(
            "stt_unavailable", "transcription service unavailable", status_code=503
        ) from exc

    # Sizes and counts only. Never the transcript, never the audio.
    logger.info(
        "transcribed audio: %d bytes, %.1f seconds, %d characters",
        len(audio),
        result.duration_seconds,
        len(result.transcript),
    )
    return TranscribeResponse(
        transcript=result.transcript, duration_seconds=result.duration_seconds
    )
