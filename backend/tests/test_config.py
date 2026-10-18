"""Settings for the STT/analysis features: defaults, env mapping, and fail-fast bounds.

``_env_file=None`` keeps the developer's ``.env`` out of the assertions; the process
environment (set via monkeypatch) is what the tests control.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_defaults_are_the_planned_integers_and_urls() -> None:
    settings = make_settings()
    assert settings.max_audio_seconds == 120
    assert settings.max_audio_mb == 10
    assert settings.commandcode_base_url == "https://api.commandcode.ai/provider/v1"
    assert settings.commandcode_model == "deepseek/deepseek-v4-flash"
    assert settings.commandcode_fallback_model == ""
    assert settings.assemblyai_api_key == ""
    assert settings.commandcode_api_key == ""


def test_env_names_map_to_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "a-key")
    monkeypatch.setenv("COMMANDCODE_API_KEY", "c-key")
    monkeypatch.setenv("COMMANDCODE_MODEL", "some/model")
    monkeypatch.setenv("COMMANDCODE_FALLBACK_MODEL", "other/model")
    monkeypatch.setenv("MAX_AUDIO_SECONDS", "30")
    monkeypatch.setenv("MAX_AUDIO_MB", "5")
    settings = Settings()
    assert settings.assemblyai_api_key == "a-key"
    assert settings.commandcode_api_key == "c-key"
    assert settings.commandcode_model == "some/model"
    assert settings.commandcode_fallback_model == "other/model"
    assert settings.max_audio_seconds == 30
    assert settings.max_audio_mb == 5


@pytest.mark.parametrize("value", ["10MB", "", "0", "-4", "601", "1000000"])
def test_bad_max_audio_seconds_fails_at_startup(value: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(max_audio_seconds=value)


@pytest.mark.parametrize("value", ["0", "-1", "26", "25MB"])
def test_bad_max_audio_mb_fails_at_startup(value: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(max_audio_mb=value)


def test_boundaries_are_inclusive() -> None:
    settings = make_settings(max_audio_seconds="5", max_audio_mb="1")
    assert (settings.max_audio_seconds, settings.max_audio_mb) == (5, 1)
    settings = make_settings(max_audio_seconds="600", max_audio_mb="25")
    assert (settings.max_audio_seconds, settings.max_audio_mb) == (600, 25)
