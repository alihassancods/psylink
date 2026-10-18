"""llm_client behaviour with a fully mocked SDK — no network, no real keys."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, BadRequestError, RateLimitError

from app.core.config import Settings
from app.services.ai import llm_client
from app.services.ai.llm_client import ChatResult, LLMError, chat_json, chat_json_result


@pytest.fixture(autouse=True)
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic settings + fresh JSON-mode probe state for every test."""
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            commandcode_api_key="test-key",
            commandcode_model="primary/model",
            commandcode_fallback_model="fallback/model",
        ),
    )
    llm_client.reset_json_mode_state()
    yield
    llm_client.reset_json_mode_state()


def status_error(cls: type[APIStatusError], status_code: int, message: str) -> APIStatusError:
    request = httpx.Request("POST", "https://api.invalid/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return cls(message, response=response, body=None)


def bad_request_error(message: str) -> BadRequestError:
    request = httpx.Request("POST", "https://api.invalid/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError(message, response=response, body=None)


class RecordingAttempt:
    """Replaces llm_client._chat_once: records kwargs per call, replays scripted outcomes."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> ChatResult:
        self.calls.append(kwargs)
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return ChatResult(content=outcome, model=kwargs["model"])


def patch_attempt(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> RecordingAttempt:
    recorder = RecordingAttempt(outcomes)
    monkeypatch.setattr(llm_client, "_chat_once", recorder)
    return recorder


@pytest.mark.asyncio
async def test_returns_content_and_records_model(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = patch_attempt(monkeypatch, ['{"risk_level": "low"}'])
    result = await chat_json_result("SYS", "USER")
    assert result.content == '{"risk_level": "low"}'
    assert result.model == "primary/model"
    assert recorder.calls[0]["json_mode"] is True  # first probe sends response_format
    assert recorder.calls[0]["model"] == "primary/model"


@pytest.mark.asyncio
async def test_json_mode_rejection_retries_prompt_only_and_remembers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection = bad_request_error("Unsupported parameter: response_format")
    recorder = patch_attempt(monkeypatch, [rejection, "second"])
    result = await llm_client._attempt(system="S", user="U", model="primary/model")
    assert result.content == "second"
    assert len(recorder.calls) == 2
    assert recorder.calls[0]["json_mode"] is True  # the probe
    assert recorder.calls[1]["json_mode"] is False  # prompt-only retry
    assert llm_client._json_mode is False

    # Remembered: the next call never sends response_format again.
    recorder2 = patch_attempt(monkeypatch, ["third"])
    await chat_json("SYS", "USER")
    assert recorder2.calls[0]["json_mode"] is False


@pytest.mark.asyncio
async def test_json_mode_rejection_must_mention_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = bad_request_error("temperature out of range")
    patch_attempt(monkeypatch, [other])
    with pytest.raises(BadRequestError):
        await llm_client._attempt(system="S", user="U", model="primary/model")
    assert llm_client._json_mode is not False  # unrelated 400 leaves JSON mode alone


@pytest.mark.asyncio
async def test_json_mode_rejection_survives_chat_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end through chat_json_result: rejection -> prompt-only success."""
    recorder = RecordingAttempt([bad_request_error("response_format not supported"), "ok"])
    monkeypatch.setattr(llm_client, "_chat_once", recorder)
    assert await chat_json_result("SYS", "USER") == ChatResult(content="ok", model="primary/model")
    assert [call["json_mode"] for call in recorder.calls] == [True, False]


@pytest.mark.asyncio
async def test_transport_error_retries_once_on_fallback_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "https://api.invalid/v1/chat/completions")
    boom = APIConnectionError(message="boom", request=request)
    recorder = patch_attempt(monkeypatch, [boom, "fb"])
    content = await chat_json("SYS", "USER")
    assert content == "fb"
    assert [call["model"] for call in recorder.calls] == ["primary/model", "fallback/model"]


@pytest.mark.asyncio
async def test_5xx_and_429_retry_on_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    for exc in (
        status_error(APIStatusError, 503, "upstream down"),
        status_error(RateLimitError, 429, "slow down"),
    ):
        llm_client.reset_json_mode_state()
        recorder = patch_attempt(monkeypatch, [exc, "fb"])
        assert await chat_json("SYS", "USER") == "fb"
        assert recorder.calls[1]["model"] == "fallback/model"


@pytest.mark.asyncio
async def test_no_fallback_configured_means_single_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            commandcode_api_key="test-key",
            commandcode_model="primary/model",
            commandcode_fallback_model="",
        ),
    )
    request = httpx.Request("POST", "https://api.invalid/v1/chat/completions")
    recorder = patch_attempt(monkeypatch, [APIConnectionError(message="boom", request=request)])
    with pytest.raises(LLMError):
        await chat_json("SYS", "USER")
    assert len(recorder.calls) == 1


@pytest.mark.asyncio
async def test_fallback_failure_raises_llmerror(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://api.invalid/v1/chat/completions")
    boom = APIConnectionError(message="boom", request=request)
    patch_attempt(monkeypatch, [boom, ValueError("x")])
    with pytest.raises(LLMError, match="ValueError"):
        await chat_json_result("SYS", "USER")


@pytest.mark.asyncio
async def test_llmerror_message_never_leaks_prompt_or_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_prompt = "transcript mentioning SECRET-PHRASE and PRIVATE-QUOTE"
    exc = status_error(APIStatusError, 500, secret_prompt)
    patch_attempt(monkeypatch, [exc, exc])  # primary + fallback both fail
    with pytest.raises(LLMError) as info:
        await chat_json("SYS", secret_prompt)
    assert "SECRET-PHRASE" not in str(info.value)
    assert "PRIVATE-QUOTE" not in str(info.value)
    assert "APIStatusError" in str(info.value) and "500" in str(info.value)


@pytest.mark.asyncio
async def test_missing_api_key_fails_fast_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client, "get_settings", lambda: Settings(_env_file=None, commandcode_api_key="")
    )
    with pytest.raises(LLMError, match="missing_api_key"):
        await chat_json("SYS", "USER")


@pytest.mark.asyncio
async def test_sdk_kwargs_via_mocked_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """_chat_once builds the right request: temp, max_tokens, response_format, messages."""
    captured: dict[str, Any] = {}

    class Completions:
        async def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            message = SimpleNamespace(content="{}")
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(model="primary/model", choices=[choice])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(llm_client, "AsyncOpenAI", lambda **_kw: fake_client)

    result = await chat_json_result("SYS-P", "USER-P")
    assert result.content == "{}"
    assert captured["temperature"] == llm_client.TEMPERATURE <= 0.2
    assert captured["max_tokens"] == 800
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"] == [
        {"role": "system", "content": "SYS-P"},
        {"role": "user", "content": "USER-P"},
    ]
