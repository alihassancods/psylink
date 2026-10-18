"""Thin async client for the Command Code Provider API (OpenAI-compatible Chat Completions).

Only chat completions are used. Failures raise :class:`LLMError`, whose message carries the
exception class and status code — never the prompt, never the model's reply. The SDK's own
retry loop is disabled (``max_retries=0``); this module retries at most once: onto prompt-only
JSON when the provider rejects ``response_format``, and onto the fallback model on transport
errors, timeouts, 429, or 5xx.
"""

import logging
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    AsyncOpenAI,
    BadRequestError,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0

#: On this provider `max_tokens` caps *reasoning* tokens too, not just the answer. The
#: models that serve /chat/completions here think out loud, so a budget sized for the JSON
#: object alone can be spent entirely on thinking and come back with empty content, or with
#: `finish_reason="length"` and half an object. 2048 was measured against the real analysis
#: prompt; a reply that still runs out is retried once at RETRY_MAX_TOKENS rather than lost.
MAX_TOKENS = 2048
RETRY_MAX_TOKENS = 4096
TEMPERATURE = 0.1

JSON_FORMAT: dict[str, str] = {"type": "json_object"}

# None = never probed; True = response_format accepted so far; False = rejected, prompt-only.
_json_mode: bool | None = None


class LLMError(Exception):
    """Terminal LLM failure. Message is sanitized: no prompt, no response content."""


class _IncompleteReply(LLMError):
    """The call succeeded but produced nothing usable: empty content, or cut off mid-JSON.

    Raised so one retry with a larger budget can rescue it. It is still an ``LLMError``, so
    a caller that does not retry degrades exactly as before.
    """


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str


def reset_json_mode_state() -> None:
    """Forget the response_format probe result (tests, or after a provider change)."""
    global _json_mode
    _json_mode = None


def _new_client() -> AsyncOpenAI:
    settings = get_settings()
    if not settings.commandcode_api_key:
        raise LLMError("missing_api_key")
    return AsyncOpenAI(
        base_url=settings.commandcode_base_url,
        api_key=settings.commandcode_api_key,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _is_json_mode_rejection(exc: BadRequestError) -> bool:
    message = (exc.message or "").lower()
    return "response_format" in message or "json_object" in message


def _is_retryable(exc: Exception) -> bool:
    """Transport trouble, timeouts, and 429/5xx — the once-retry-onto-fallback cases."""
    if isinstance(exc, APIConnectionError):  # includes APITimeoutError
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _sanitize(exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        return f"{type(exc).__name__} (status {exc.status_code})"
    return type(exc).__name__


async def _chat_once(
    *, system: str, user: str, model: str, json_mode: bool, max_tokens: int = MAX_TOKENS
) -> ChatResult:
    client = _new_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = JSON_FORMAT
    completion = await client.chat.completions.create(**kwargs)
    choice = completion.choices[0]
    content = choice.message.content
    if not content:
        # A reasoning model that spent the whole budget thinking. Retryable: the next
        # attempt gets a larger ceiling, which is what actually unblocks it.
        raise _IncompleteReply("empty_completion")
    if getattr(choice, "finish_reason", None) == "length":
        # Provably half an object — parsing it would be guesswork.
        raise _IncompleteReply("truncated_completion")
    return ChatResult(content=content, model=getattr(completion, "model", None) or model)


async def chat_json_result(system: str, user: str, *, model: str | None = None) -> ChatResult:
    """Like :func:`chat_json` but also reports which model actually answered."""
    global _json_mode
    settings = get_settings()
    primary = model or settings.commandcode_model
    fallback = settings.commandcode_fallback_model
    if _json_mode is None:
        _json_mode = True

    try:
        return await _attempt(system=system, user=user, model=primary)
    except _IncompleteReply as exc:
        # Same model, bigger budget: the reply was well-formed, just starved of room.
        logger.info("reply was incomplete (%s); retrying with a larger budget", exc)
        try:
            return await _attempt(
                system=system, user=user, model=primary, max_tokens=RETRY_MAX_TOKENS
            )
        except _IncompleteReply as second:
            raise LLMError(f"incomplete_completion: {second}") from second
        except APIError as second:
            raise LLMError(_sanitize(second)) from second
    except LLMError:
        raise
    except APIError as exc:
        if not _is_retryable(exc) or not fallback:
            raise LLMError(_sanitize(exc)) from exc
        logger.warning("primary model failed with %s; trying fallback model", _sanitize(exc))
        try:
            return await _attempt(system=system, user=user, model=fallback)
        except _IncompleteReply as second:
            raise LLMError(f"incomplete_completion: {second}") from second
        except Exception as second:
            raise LLMError(_sanitize(second)) from second


async def _attempt(
    *, system: str, user: str, model: str, max_tokens: int = MAX_TOKENS
) -> ChatResult:
    """One model attempt; may consume a second call when JSON mode gets rejected.

    ``_json_mode`` is True-or-unprobed here: only an explicit rejection (False) turns
    ``response_format`` off, so a None state still probes.
    """
    global _json_mode
    try:
        return await _chat_once(
            system=system,
            user=user,
            model=model,
            json_mode=_json_mode is not False,
            max_tokens=max_tokens,
        )
    except BadRequestError as exc:
        if _json_mode is False or not _is_json_mode_rejection(exc):
            raise
        logger.info("provider rejected response_format; falling back to prompt-only JSON")
        _json_mode = False
        return await _chat_once(
            system=system, user=user, model=model, json_mode=False, max_tokens=max_tokens
        )


async def chat_json(system: str, user: str, *, model: str | None = None) -> str:
    """Return the assistant message as text, asking for a JSON object.

    Raises:
        LLMError: on any terminal failure (missing key, non-retryable provider error,
            a retryable error with no fallback model configured, empty completion).
    """
    result = await chat_json_result(system, user, model=model)
    return result.content
