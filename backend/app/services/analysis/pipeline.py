"""The combined pipeline: one LLM call for summary + classification, wrapped in hard floors.

Order of guarantees:

1. The keyword screen runs first and is a floor: the model can raise risk, never lower it.
2. One call produces both the summary and the classification.
3. An unparseable reply gets exactly one stricter retry; after that the LLM contributes
   nothing (``analysis is None``).
4. Guardrails then edit the reply: a quote that is not verbatim is dropped (confidence
   falls to "low"), and a diagnosing summary earns one corrective retry before the whole
   analysis is discarded.
5. Nothing usable and no keyword hit ⇒ ``final_risk="moderate"`` with ``risk_source=
   "fallback"``. Failing safe means an unanalysable check-in is never reported as calm.
6. ``AnalysisOutcome`` always comes back; only an empty transcript raises.
"""

import logging

from app.services.ai.llm_client import ChatResult, LLMError, chat_json_result
from app.services.analysis.guardrails import (
    contains_diagnostic_language,
    parse_analysis,
    validate_evidence,
)
from app.services.analysis.keywords import screen_text
from app.services.analysis.prompt import (
    SYSTEM_PROMPT,
    build_diagnostic_retry_prompt,
    build_retry_prompt,
    build_user_prompt,
)
from app.services.analysis.schemas import (
    Analysis,
    AnalysisOutcome,
    RiskLevel,
    RiskSource,
    higher_risk,
)

logger = logging.getLogger(__name__)


async def _request(user_prompt: str) -> ChatResult | None:
    """One provider call; ``None`` means it failed. LLMError never escapes the pipeline."""
    try:
        return await chat_json_result(SYSTEM_PROMPT, user_prompt)
    except LLMError:
        logger.warning("analysis: llm call failed (reason withheld, no prompt in logs)")
        return None


def _parse(reply: ChatResult | None) -> Analysis | None:
    if reply is None:
        return None
    try:
        return parse_analysis(reply.content)
    except ValueError:
        logger.info("analysis: reply was not valid analysis json")
        return None


def _risk_source(keyword: RiskLevel | None, llm: RiskLevel | None) -> RiskSource:
    if keyword is not None and llm is not None:
        return "both"
    if keyword is not None:
        return "keyword"
    if llm is not None:
        return "llm"
    return "fallback"


async def analyze_checkin(transcript: str) -> AnalysisOutcome:
    """Screen and analyse one check-in, returning the floor-adjusted risk.

    Raises:
        ValueError: the transcript is empty or whitespace only — there is nothing to analyse.
    """
    text = transcript.strip()
    if not text:
        raise ValueError("transcript is empty")

    keyword_risk: RiskLevel | None = "high" if screen_text(text) else None

    analysis: Analysis | None = None
    model_used: str | None = None

    reply = await _request(build_user_prompt(text))
    if reply is not None:
        analysis, model_used = _parse(reply), reply.model
        if analysis is None:
            # Unparseable or schema-violating: exactly one stricter retry.
            retry = await _request(build_retry_prompt(text))
            analysis, model_used = _parse(retry), (retry.model if retry is not None else model_used)

    if analysis is not None and contains_diagnostic_language(analysis.summary):
        corrected = await _request(build_diagnostic_retry_prompt(text))
        replacement = _parse(corrected)
        if replacement is not None and not contains_diagnostic_language(replacement.summary):
            analysis = replacement
            model_used = corrected.model if corrected is not None else model_used
        else:
            # Still diagnosing after a correction: the summary is unusable, so is the reply.
            logger.warning("analysis: discarded reply that kept diagnostic language")
            analysis = None

    if analysis is not None:
        evidence, rejected = validate_evidence(analysis.risk_evidence, text)
        if rejected or evidence != analysis.risk_evidence:
            # A quote the patient never said: drop it, and stop trusting the confidence.
            analysis = analysis.model_copy(update={"risk_evidence": evidence, "confidence": "low"})

    llm_risk: RiskLevel | None = None
    if analysis is not None:
        llm_risk = analysis.risk_level
        # The model's own quote can be the strongest signal in the reply: it may raise risk,
        # and because the quote was verbatim it is screened with the same floor rules.
        if analysis.risk_evidence is not None and screen_text(analysis.risk_evidence):
            llm_risk = "high"

    final_risk = higher_risk(keyword_risk, llm_risk)
    if final_risk is None:
        final_risk, source = "moderate", "fallback"
    else:
        source = _risk_source(keyword_risk, llm_risk)

    return AnalysisOutcome(
        analysis=analysis,
        final_risk=final_risk,
        risk_source=source,
        show_crisis_resources=AnalysisOutcome.crisis_visible(final_risk),
        model_used=model_used,
    )
