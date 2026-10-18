"""One error shape for the API's own failures.

``HTTPException`` with a ``detail`` object: ``{"detail": {"code": ..., "message": ...}}``.
The code is the stable, machine-readable half the frontend switches on; the message is
human-readable and never carries patient content. FastAPI's own 422 validation errors keep
their native shape — this covers only deliberate refusals.
"""

from typing import Any

from fastapi import HTTPException, status

#: Codes the frontend can rely on. Anything it does not know should fall back to typing.
ERROR_CODES = frozenset(
    {
        "unsupported_audio",
        "empty_audio",
        "audio_too_large",
        "audio_too_long",
        "rate_limited",
        "consent_required",
        "empty_transcript",
        "stt_timeout",
        "stt_unavailable",
        "stt_failed",
        "checkin_required",
        "checkin_not_stored",
        "invite_invalid",
        "invite_not_stored",
        "consent_not_found",
        "consent_not_stored",
    }
)


def api_error(
    code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST
) -> HTTPException:
    """Build the standard refusal. ``code`` must be one of :data:`ERROR_CODES`."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code: {code!r}")
    detail: dict[str, Any] = {"code": code, "message": message}
    return HTTPException(status_code=status_code, detail=detail)
