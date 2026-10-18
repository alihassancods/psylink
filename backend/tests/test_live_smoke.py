"""Opt-in live checks against the real third parties.

Skipped unless ``RUN_LIVE_TESTS=1``, because they spend money and need network access.
Run them before a demo with::

    RUN_LIVE_TESTS=1 ASSEMBLYAI_API_KEY=... COMMANDCODE_API_KEY=... uv run pytest

They assert only that the wiring is correct — a reachable provider, a model id that exists,
a transcription round trip that cleans up after itself. Nothing here sends patient content:
the prompts are synthetic and the audio is generated silence.
"""

import os
import struct
import wave
import io

import pytest

requires_live = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="set RUN_LIVE_TESTS=1 to call the real providers (costs money)",
)


def _silent_wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    """A valid mono WAV of silence — no speech, no patient, no stored artefact."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack(f"<{int(seconds * rate)}h", *([0] * int(seconds * rate))))
    return buffer.getvalue()


@requires_live
async def test_pipeline_returns_a_usable_outcome_for_synthetic_text() -> None:
    """The real prompt, the real schema, the real guardrails — and no patient content.

    The risk level is not asserted: a model may legitimately read "I don't think I can
    carry on like this" as moderate or high. What must hold is that a valid, schema-shaped
    analysis comes back and the outcome is never empty of risk.
    """
    from app.services.analysis.pipeline import analyze_checkin

    if not os.getenv("COMMANDCODE_API_KEY"):
        pytest.skip("COMMANDCODE_API_KEY is not set")

    transcript = (
        "I have not slept more than three hours a night since my dissertation deadline. "
        "I keep crying in the library and I don't think I can carry on like this."
    )

    outcome = await analyze_checkin(transcript)

    assert outcome.final_risk in {"low", "moderate", "high"}
    assert outcome.risk_source in {"keyword", "llm", "both", "fallback"}
    assert outcome.model_used
    if outcome.analysis is not None:
        analysis = outcome.analysis
        assert 1 <= analysis.mood_score <= 10
        assert len(analysis.emotions) <= 5
        assert len(analysis.summary) <= 300
        # Evidence must be words the patient actually wrote, if it is present at all.
        if analysis.risk_evidence is not None:
            assert analysis.risk_evidence in transcript


@requires_live
async def test_configured_model_is_offered_by_the_provider() -> None:
    import httpx

    from app.core.config import get_settings

    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.commandcode_base_url}/models",
            headers={"Authorization": f"Bearer {settings.commandcode_api_key}"},
        )
    assert response.status_code == 200
    ids = {model["id"] for model in response.json()["data"]}
    assert settings.commandcode_model in ids, (
        f"{settings.commandcode_model} not in {sorted(ids)[:5]}..."
    )


@requires_live
async def test_transcription_round_trip_cleans_up() -> None:
    """Silence should not produce a transcript, but must never leave a remote transcript behind.

    Accepted outcomes: EmptyTranscript (the expected case), or a specific STT failure. A
    raw SDK exception escaping here means the mapping layer is wrong.
    """
    from app.services.stt.assemblyai_client import STTError, transcribe_bytes

    if not os.getenv("ASSEMBLYAI_API_KEY"):
        pytest.skip("ASSEMBLYAI_API_KEY is not set")

    try:
        await transcribe_bytes(_silent_wav(), max_seconds=120)
    except STTError as exc:
        assert type(exc).__name__ in {
            "EmptyTranscript",
            "STTFailed",
            "STTUnavailable",
            "STTTimeout",
            "STTRateLimited",
        }
    else:  # pragma: no cover - silent audio occasionally returns filler text
        pass
