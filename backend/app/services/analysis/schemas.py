"""Pydantic models for analysis output and the pipeline's final outcome.

``Analysis`` is what the LLM must return. Validation is intentionally strict on the fields
that feed safety decisions (risk level, confidence) and forgiving on presentation (emotions
are lowercased and trimmed to five). ``AnalysisOutcome`` is what the pipeline hands the API:
it always exists, even when the LLM failed, because the risk floor must survive the failure.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskLevel = Literal["low", "moderate", "high"]
RiskSource = Literal["keyword", "llm", "both", "fallback"]
Confidence = Literal["low", "medium", "high"]

#: Ordering used by the guardrail that takes the higher of two risk levels.
RISK_ORDER: dict[RiskLevel, int] = {"low": 0, "moderate": 1, "high": 2}

#: Risk levels that make the frontend show crisis resources.
CRISIS_LEVELS: frozenset[RiskLevel] = frozenset({"moderate", "high"})

SYMPTOM_NAMES = (
    "sleep",
    "appetite",
    "energy",
    "anxiety",
    "concentration",
    "social_withdrawal",
    "irritability",
)


def higher_risk(a: RiskLevel | None, b: RiskLevel | None) -> RiskLevel | None:
    """The higher of two levels; ``None`` means "unknown", which never wins."""
    candidates = [level for level in (a, b) if level is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda level: RISK_ORDER[level])


class Symptoms(BaseModel):
    """0-3 severity per symptom; ``None`` means the patient did not mention it.

    ``None`` is never coerced to 0 — "not mentioned" and "no problem" are different answers.
    """

    model_config = ConfigDict(extra="ignore")

    sleep: int | None = Field(default=None, ge=0, le=3)
    appetite: int | None = Field(default=None, ge=0, le=3)
    energy: int | None = Field(default=None, ge=0, le=3)
    anxiety: int | None = Field(default=None, ge=0, le=3)
    concentration: int | None = Field(default=None, ge=0, le=3)
    social_withdrawal: int | None = Field(default=None, ge=0, le=3)
    irritability: int | None = Field(default=None, ge=0, le=3)


class Analysis(BaseModel):
    """One LLM reading of one check-in transcript."""

    model_config = ConfigDict(extra="ignore")

    mood_score: int = Field(ge=1, le=10)
    emotions: list[str] = Field(default_factory=list, max_length=5)
    symptoms: Symptoms = Field(default_factory=Symptoms)
    risk_level: RiskLevel
    risk_evidence: str | None = None
    summary: str = Field(min_length=1, max_length=300)
    confidence: Confidence

    @field_validator("emotions", mode="before")
    @classmethod
    def _clean_emotions(cls, value: object) -> list[str]:
        """Lowercase, drop blanks, and keep at most five — trimmed, not rejected."""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("emotions must be a list")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("emotions must be strings")
            word = item.strip().lower()
            if word and word not in cleaned:
                cleaned.append(word)
        return cleaned[:5]

    @field_validator("summary", "risk_evidence")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("risk_evidence")
    @classmethod
    def _evidence_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("risk_evidence must be null or a quote")
        return value


class AnalysisOutcome(BaseModel):
    """Pipeline result: the floor-adjusted risk plus what produced it.

    ``analysis`` is ``None`` when the LLM failed or was rejected by a guardrail; ``final_risk``
    is always populated, falling back to ``"moderate"`` when nothing else could be learned.
    """

    model_config = ConfigDict(frozen=True)

    analysis: Analysis | None
    final_risk: RiskLevel
    risk_source: RiskSource
    show_crisis_resources: bool
    model_used: str | None

    @staticmethod
    def crisis_visible(risk: RiskLevel) -> bool:
        return risk in CRISIS_LEVELS
