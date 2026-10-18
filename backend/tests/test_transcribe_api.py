"""``POST /api/transcribe`` end to end, with the SDK layer faked.

Auth, consent, the upload-shape rules, the size and rate limits, and the mapping of every
STT failure onto a status the frontend can act on. Transcription itself is a stub — the
client that talks to AssemblyAI has its own suite.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.api import transcribe as transcribe_module
from app.core.config import Settings
from app.core.ratelimit import transcribe_limiter
from app.models.profile import UserRole
from app.services.db import service_client
from app.services.stt.assemblyai_client import (
    AudioTooLong,
    EmptyTranscript,
    STTFailed,
    STTRateLimited,
    STTTimeout,
    STTUnavailable,
    TranscriptionResult,
)

WEBM = b"\x1a\x45\xdf\xa3fake-audio"
OK = TranscriptionResult(transcript="I slept badly", duration_seconds=8.5)


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    transcribe_limiter.reset()
    yield
    transcribe_limiter.reset()


@pytest.fixture
def stub_stt(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], list[dict[str, Any]]]:
    """Replace the transcription call and record what the endpoint handed it."""
    calls: list[dict[str, Any]] = []

    def install(outcome: Any) -> list[dict[str, Any]]:
        async def fake_transcribe(
            audio: bytes, *, language_code: str = "en", max_seconds: int | None = None
        ):
            calls.append({"audio": audio, "max_seconds": max_seconds, "language": language_code})
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(transcribe_module, "transcribe_bytes", fake_transcribe)
        return calls

    return install


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Keep the size tests small: 1 MB and 30 seconds, without touching the real .env."""

    def apply(*, mb: int = 1, seconds: int = 30) -> None:
        monkeypatch.setattr(
            transcribe_module,
            "get_settings",
            lambda: Settings(_env_file=None, max_audio_mb=mb, max_audio_seconds=seconds),
        )

    return apply


@pytest.fixture
async def consented_patient(seed_profile, seed_consent) -> dict[str, UUID]:
    patient = await seed_profile(role=UserRole.PATIENT, display_name="P")
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="C")
    await seed_consent(patient, clinician)
    return {"patient": patient, "clinician": clinician}


def audio_headers(token: str, content_type: str = "audio/webm") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": content_type}


# --- happy path ---------------------------------------------------------------------


async def test_returns_the_transcript_and_duration(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    calls = stub_stt(OK)
    token = make_token(consented_patient["patient"])

    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(token, "audio/webm;codecs=opus"),
        content=WEBM,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"transcript": "I slept badly", "duration_seconds": 8.5}
    # The bytes reached the client untouched and the configured cap was passed down.
    assert calls[0]["audio"] == WEBM
    assert calls[0]["max_seconds"] == 30


@pytest.mark.parametrize(
    "content_type",
    ["audio/webm", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg", "audio/mpeg"],
)
async def test_recorder_output_types_are_accepted(
    api_client, limits, stub_stt, consented_patient, make_token, content_type
) -> None:
    limits()
    stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"]), content_type),
        content=WEBM,
    )
    assert response.status_code == 200, content_type


async def test_multipart_upload_is_unwrapped_to_the_file_part(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    calls = stub_stt(OK)
    multipart = (
        b'--BOUND\r\nContent-Disposition: form-data; name="file"; filename="a.webm"\r\n'
        b"Content-Type: audio/webm\r\n\r\n" + WEBM + b"\r\n--BOUND--\r\n"
    )

    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(
            make_token(consented_patient["patient"]), "multipart/form-data; boundary=BOUND"
        ),
        content=multipart,
    )

    assert response.status_code == 200, response.text
    assert calls[0]["audio"] == WEBM  # just the part body, no headers or boundary


# --- upload validation ---------------------------------------------------------------


async def test_unsupported_content_type_is_400_before_transcription(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    calls = stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"]), "text/plain"),
        content=b"not audio",
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_audio"
    assert calls == []


async def test_missing_content_type_is_refused(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers={"Authorization": f"Bearer {make_token(consented_patient['patient'])}"},
        content=WEBM,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_audio"


async def test_multipart_without_a_boundary_is_400(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"]), "multipart/form-data"),
        content=WEBM,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported_audio"


async def test_multipart_with_only_a_text_field_is_400(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    stub_stt(OK)
    body = b'--B\r\nContent-Disposition: form-data; name="note"\r\n\r\nhello\r\n--B--\r\n'
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(
            make_token(consented_patient["patient"]), "multipart/form-data; boundary=B"
        ),
        content=body,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_audio"


async def test_empty_body_is_400(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"])),
        content=b"",
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "empty_audio"


async def test_oversize_is_413_from_the_content_length_header(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits(mb=1)
    calls = stub_stt(OK)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"])),
        content=b"x" * (2 * 1024 * 1024),
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "audio_too_large"
    assert calls == []  # refused before anything was transcribed


async def test_oversize_chunked_upload_is_413_without_a_header(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    """No Content-Length to trust: the streaming cap still stops it."""
    limits(mb=1)
    stub_stt(OK)

    async def body():
        for _ in range(6):
            yield b"x" * (512 * 1024)

    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"])),
        content=body(),
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "audio_too_large"


# --- authorisation and consent -------------------------------------------------------


async def test_requires_a_bearer_token(api_client, limits) -> None:
    limits()
    response = await api_client.post(
        "/api/transcribe", headers={"Content-Type": "audio/webm"}, content=WEBM
    )
    assert response.status_code == 401


async def test_clinician_cannot_transcribe(
    api_client, limits, stub_stt, seed_profile, make_token
) -> None:
    limits()
    stub_stt(OK)
    clinician = await seed_profile(role=UserRole.CLINICIAN)
    response = await api_client.post(
        "/api/transcribe", headers=audio_headers(make_token(clinician)), content=WEBM
    )
    assert response.status_code == 403
    assert "requires role" in response.text


async def test_patient_without_consent_is_403(
    api_client, limits, stub_stt, seed_profile, make_token
) -> None:
    limits()
    stub_stt(OK)
    lonely = await seed_profile(role=UserRole.PATIENT)
    response = await api_client.post(
        "/api/transcribe", headers=audio_headers(make_token(lonely)), content=WEBM
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required"


async def test_revoked_consent_is_403(
    api_client, limits, stub_stt, seed_profile, seed_consent, make_token
) -> None:
    limits()
    stub_stt(OK)
    patient = await seed_profile(role=UserRole.PATIENT)
    clinician = await seed_profile(role=UserRole.CLINICIAN)
    consent_id = await seed_consent(patient, clinician)

    async with service_client() as db:
        await db.update(
            "consents",
            {"revoked_at": datetime.now(UTC)},
            where="id = :id",
            params={"id": str(consent_id)},
        )

    response = await api_client.post(
        "/api/transcribe", headers=audio_headers(make_token(patient)), content=WEBM
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required"


# --- rate limiting --------------------------------------------------------------------


async def test_eleventh_upload_in_the_hour_is_429(
    api_client, limits, stub_stt, consented_patient, make_token
) -> None:
    limits()
    stub_stt(OK)
    headers = audio_headers(make_token(consented_patient["patient"]))

    codes = [
        (await api_client.post("/api/transcribe", headers=headers, content=WEBM)).status_code
        for _ in range(12)
    ]

    assert codes[:10] == [200] * 10
    assert codes[10:] == [429, 429]


async def test_rate_limit_is_per_patient(
    api_client, limits, stub_stt, seed_profile, seed_consent, make_token
) -> None:
    limits()
    stub_stt(OK)
    a = await seed_profile(role=UserRole.PATIENT)
    b = await seed_profile(role=UserRole.PATIENT)
    clinician = await seed_profile(role=UserRole.CLINICIAN)
    await seed_consent(a, clinician)
    await seed_consent(b, clinician)

    headers_a = audio_headers(make_token(a))
    for _ in range(10):
        assert (
            await api_client.post("/api/transcribe", headers=headers_a, content=WEBM)
        ).status_code == 200
    assert (
        await api_client.post("/api/transcribe", headers=headers_a, content=WEBM)
    ).status_code == 429

    # The other patient still has their whole budget.
    assert (
        await api_client.post("/api/transcribe", headers=audio_headers(make_token(b)), content=WEBM)
    ).status_code == 200


# --- STT failures mapped to the documented codes ---------------------------------------


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (STTRateLimited("busy"), 429, "rate_limited"),
        (STTTimeout("late"), 504, "stt_timeout"),
        (EmptyTranscript("silence"), 502, "empty_transcript"),
        (STTFailed("clip rejected"), 502, "stt_failed"),
        (STTUnavailable("down"), 503, "stt_unavailable"),
        (AudioTooLong("too long"), 400, "audio_too_long"),
    ],
)
async def test_stt_errors_use_the_standard_shape(
    api_client, limits, stub_stt, consented_patient, make_token, error, status_code, code
) -> None:
    limits()
    stub_stt(error)
    response = await api_client.post(
        "/api/transcribe",
        headers=audio_headers(make_token(consented_patient["patient"])),
        content=WEBM,
    )
    assert response.status_code == status_code
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert isinstance(detail["message"], str) and detail["message"]
