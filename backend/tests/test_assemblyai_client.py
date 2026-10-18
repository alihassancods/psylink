"""The AssemblyAI client against a fake SDK — no network, no audio on disk.

The behaviours that matter here are the ones the patient cannot see: the remote transcript
being deleted on every path that got an id, the audio going to the SDK as memory only, and
the failure modes arriving as the right exception so the endpoint can map them.
"""

import logging
from typing import Any, ClassVar

import assemblyai
import pytest
from assemblyai import AssemblyAIError, TranscriptStatus
from assemblyai.types import TranscriptError

from app.core.config import Settings
from app.services.stt import assemblyai_client as stt
from app.services.stt.assemblyai_client import (
    AudioTooLong,
    EmptyTranscript,
    STTFailed,
    STTRateLimited,
    STTTimeout,
    STTUnavailable,
    transcribe_bytes,
)

AUDIO = b"\x1a\x45\xdf\xa3fake-webm-bytes"
TRANSCRIPT_ID = "tr-123"


class FakeTranscript:
    def __init__(
        self,
        *,
        text: str | None = "  hello there  ",
        duration: Any = 3.0,
        status=TranscriptStatus.completed,
        error: str | None = None,
        poll_error: Exception | None = None,
    ) -> None:
        self.id = TRANSCRIPT_ID
        self.text = text
        self.audio_duration = duration
        self.status = status
        self.error = error
        self.poll_error = poll_error
        self.polled = False

    def wait_for_completion(self, *, poll_timeout: float | None = None) -> FakeTranscript:
        self.polled = True
        self.poll_timeout = poll_timeout
        if self.poll_error is not None:
            raise self.poll_error
        return self


class FakeTranscriber:
    """Stands in for assemblyai's Transcriber and records what was handed to it."""

    instances: ClassVar[list[FakeTranscriber]] = []

    def __init__(self, *, api_key: str | None = None, config: Any = None) -> None:
        self.api_key = api_key
        self.config = config
        self.submitted: list[Any] = []
        self.submit_config: Any = None
        FakeTranscriber.instances.append(self)

    def submit(self, data: Any, *, config: Any = None) -> FakeTranscript:
        self.submitted.append(data)
        self.submit_config = config
        outcome = FakeTranscriber.next_outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def transcribe(self, data: Any, *, config: Any = None, poll_timeout: float | None = None):
        raise AssertionError("transcribe() must not be used: submit+wait keeps the id for deletion")


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch: pytest.MonkeyPatch):
    """Wire the module onto fakes and reset the call log for every test."""

    def install(outcome: Any) -> type[FakeTranscriber]:
        FakeTranscriber.instances = []
        FakeTranscriber.next_outcome = outcome
        monkeypatch.setattr(stt, "Transcriber", FakeTranscriber)
        monkeypatch.setattr(
            stt, "get_settings", lambda: Settings(_env_file=None, assemblyai_api_key="k")
        )
        return FakeTranscriber

    deleted: list[str] = []

    def fake_delete(transcript_id: str) -> None:
        if FakeTranscriber.delete_error is not None:
            raise FakeTranscriber.delete_error
        deleted.append(transcript_id)

    FakeTranscriber.delete_error = None
    monkeypatch.setattr(stt.Transcript, "delete_by_id", staticmethod(fake_delete))
    install(FakeTranscript())
    yield install, deleted, lambda error: setattr(FakeTranscriber, "delete_error", error)
    FakeTranscriber.instances = []
    FakeTranscriber.delete_error = None


# --- happy path -------------------------------------------------------------------


async def test_returns_stripped_text_and_duration(fake_sdk) -> None:
    install, deleted, _ = fake_sdk
    transcriber_cls = install(FakeTranscript(text="  I slept badly  ", duration=12.5))
    result = await transcribe_bytes(AUDIO)
    assert result.transcript == "I slept badly"
    assert result.duration_seconds == 12.5
    assert deleted == [TRANSCRIPT_ID]
    # Audio travelled as memory: exactly what was uploaded, no path, no file object.
    assert transcriber_cls.instances[0].submitted == [AUDIO]


async def test_no_temp_file_is_created_for_the_audio(fake_sdk) -> None:
    import os
    import tempfile

    before = set(os.listdir(tempfile.gettempdir()))
    install, _, _ = fake_sdk
    install(FakeTranscript())
    await transcribe_bytes(AUDIO)
    assert set(os.listdir(tempfile.gettempdir())) == before


async def test_default_language_is_english(fake_sdk) -> None:
    install, _, _ = fake_sdk
    transcriber_cls = install(FakeTranscript())
    await transcribe_bytes(AUDIO)
    assert transcriber_cls.instances[0].submit_config.language_code == "en"


async def test_polling_is_bounded_by_the_documented_timeout(fake_sdk) -> None:
    install, _, _ = fake_sdk
    transcript = FakeTranscript()
    install(transcript)
    await transcribe_bytes(AUDIO)
    assert transcript.poll_timeout == stt.POLL_TIMEOUT_SECONDS
    assert transcript.polled is True


# --- the deletion guarantee -------------------------------------------------------


async def test_remote_transcript_is_deleted_even_when_transcription_fails(fake_sdk) -> None:
    install, deleted, _ = fake_sdk
    install(FakeTranscript(status=TranscriptStatus.error, error="bad audio", text=None))
    with pytest.raises(STTFailed):
        await transcribe_bytes(AUDIO)
    assert deleted == [TRANSCRIPT_ID]


async def test_remote_transcript_is_deleted_after_a_polling_timeout(fake_sdk) -> None:
    """The id is captured at submission precisely so this path can still clean up."""
    install, deleted, _ = fake_sdk
    install(FakeTranscript(poll_error=TranscriptError("polling timed out", status_code=None)))
    with pytest.raises(STTTimeout):
        await transcribe_bytes(AUDIO)
    assert deleted == [TRANSCRIPT_ID]


async def test_remote_transcript_is_deleted_when_the_text_is_empty(fake_sdk) -> None:
    install, deleted, _ = fake_sdk
    install(FakeTranscript(text="   ", duration=2.0))
    with pytest.raises(EmptyTranscript):
        await transcribe_bytes(AUDIO)
    assert deleted == [TRANSCRIPT_ID]


async def test_delete_failure_is_reported_by_id_only_and_keeps_the_answer(fake_sdk, caplog) -> None:
    install, deleted, fail_delete = fake_sdk
    install(FakeTranscript(text="I am fine"))
    fail_delete(AssemblyAIError("delete exploded", status_code=500))
    with caplog.at_level(logging.WARNING):
        result = await transcribe_bytes(AUDIO)
    assert result.transcript == "I am fine"
    assert deleted == []
    text = " ".join(record.getMessage() for record in caplog.records)
    assert TRANSCRIPT_ID in text
    assert "I am fine" not in text  # content never reaches the log


# --- failure mapping --------------------------------------------------------------


async def test_empty_transcript_raises(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript(text=None))
    with pytest.raises(EmptyTranscript):
        await transcribe_bytes(AUDIO)


async def test_error_status_raises_stt_failed(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript(status=TranscriptStatus.error, error="could not decode", text=None))
    with pytest.raises(STTFailed):
        await transcribe_bytes(AUDIO)


async def test_error_status_about_length_raises_audio_too_long(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript(status=TranscriptStatus.error, error="audio too long", text=None))
    with pytest.raises(AudioTooLong):
        await transcribe_bytes(AUDIO)


async def test_rate_limit_status_maps_to_stt_rate_limited(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(AssemblyAIError("too many parallel jobs", status_code=429))
    with pytest.raises(STTRateLimited):
        await transcribe_bytes(AUDIO)


async def test_server_error_maps_to_unavailable(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(AssemblyAIError("upstream 503", status_code=503))
    with pytest.raises(STTUnavailable):
        await transcribe_bytes(AUDIO)


async def test_missing_api_key_is_reported_before_any_request(fake_sdk, monkeypatch) -> None:
    _, _, _ = fake_sdk
    monkeypatch.setattr(
        stt, "get_settings", lambda: Settings(_env_file=None, assemblyai_api_key="")
    )
    with pytest.raises(STTUnavailable, match="ASSEMBLYAI_API_KEY"):
        await transcribe_bytes(AUDIO)
    assert FakeTranscriber.instances == []


# --- the duration gate ------------------------------------------------------------


async def test_longer_than_max_seconds_raises_and_still_deletes(fake_sdk) -> None:
    install, deleted, _ = fake_sdk
    install(FakeTranscript(text="a very long monologue", duration=121.0))
    with pytest.raises(AudioTooLong):
        await transcribe_bytes(AUDIO, max_seconds=120)
    assert deleted == [TRANSCRIPT_ID]


async def test_at_the_limit_is_accepted(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript(text="exactly at the cap", duration=120.0))
    result = await transcribe_bytes(AUDIO, max_seconds=120)
    assert result.duration_seconds == 120.0


async def test_duration_is_not_gated_when_no_limit_is_given(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript(text="long but caller handles it", duration=900.0))
    result = await transcribe_bytes(AUDIO)
    assert result.duration_seconds == 900.0


async def test_missing_duration_does_not_break_the_gate(fake_sdk) -> None:
    """AssemblyAI has reported None duration; text must still come back."""
    install, _, _ = fake_sdk
    install(FakeTranscript(text="got words", duration=None))
    result = await transcribe_bytes(AUDIO, max_seconds=120)
    assert result.transcript == "got words"
    assert result.duration_seconds == 0.0


async def test_global_client_key_is_set_so_delete_by_id_works(fake_sdk) -> None:
    install, _, _ = fake_sdk
    install(FakeTranscript())
    await transcribe_bytes(AUDIO)
    assert assemblyai.settings.api_key == "k"
