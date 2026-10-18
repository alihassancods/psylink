"""Guardrail and schema behaviour — pure functions, no model, no network."""

import json

import pytest

from app.services.analysis.guardrails import (
    contains_diagnostic_language,
    parse_analysis,
    validate_evidence,
)
from app.services.analysis.schemas import Analysis, AnalysisOutcome, higher_risk

TRANSCRIPT = "I have been sad since term started and sleep badly"

VALID = {
    "mood_score": 3,
    "emotions": ["Sad", "tired", "hopeless", "anxious", "lonely", "numb"],
    "symptoms": {
        "sleep": 2,
        "appetite": None,
        "energy": 3,
        "anxiety": None,
        "concentration": 2,
        "social_withdrawal": 1,
        "irritability": None,
    },
    "risk_level": "low",
    "risk_evidence": None,
    "summary": "The patient reports low mood and poor sleep since the term started.",
    "confidence": "medium",
}


def payload(**overrides: object) -> str:
    return json.dumps({**VALID, **overrides})


# --- parse_analysis ---------------------------------------------------------------


def test_parses_plain_json() -> None:
    analysis = parse_analysis(payload())
    assert analysis.risk_level == "low"
    assert analysis.mood_score == 3


def test_parses_fenced_json() -> None:
    assert parse_analysis("```json\n" + payload() + "\n```").risk_level == "low"
    assert parse_analysis("```\n" + payload() + "\n```").risk_level == "low"


def test_parses_object_wrapped_in_prose() -> None:
    assert parse_analysis("Here you go: " + payload() + " Hope that helps.").summary


def test_rejects_non_json() -> None:
    for bad in ("", "not json at all", "{", '{"risk_level": }'):
        with pytest.raises(ValueError):
            parse_analysis(bad)


def test_rejects_missing_required_field() -> None:
    missing = {k: v for k, v in VALID.items() if k != "mood_score"}
    with pytest.raises(ValueError):
        parse_analysis(json.dumps(missing))


def test_rejects_out_of_range_values() -> None:
    for overrides in (
        {"mood_score": 11},
        {"mood_score": 0},
        {"risk_level": "severe"},
        {"confidence": "certain"},
        {"symptoms": {**VALID["symptoms"], "sleep": 4}},
    ):
        with pytest.raises(ValueError):
            parse_analysis(payload(**overrides))


def test_emotions_are_lowercased_deduped_and_capped_at_five() -> None:
    analysis = parse_analysis(payload(emotions=["Sad", "SAD", "angry", "Tired", "numb", "lost"]))
    assert analysis.emotions == ["sad", "angry", "tired", "numb", "lost"]
    assert len(analysis.emotions) == 5


def test_summary_over_300_chars_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_analysis(payload(summary="x" * 301))


def test_unmentioned_symptoms_stay_null_not_zero() -> None:
    analysis = parse_analysis(payload(symptoms=dict.fromkeys(VALID["symptoms"], None)))
    assert analysis.symptoms.sleep is None
    assert analysis.symptoms.model_dump()["anxiety"] is None


# --- diagnostic language ----------------------------------------------------------


@pytest.mark.parametrize(
    "summary",
    [
        "The patient has depression and is struggling.",
        "Signs consistent with bipolar disorder.",
        "The patient presents with an anxiety disorder.",
        "This looks like clinical depression.",
        "The patient may be experiencing psychosis.",
        "Symptoms suggest an eating disorder.",
        "The patient seems manic this week.",
        "HAS DEPRESSION, reports poor sleep",  # case-insensitive
        "possible personality disorder noted",
        "The patient is depressed and tired",
    ],
)
def test_diagnostic_summaries_are_rejected(summary: str) -> None:
    assert contains_diagnostic_language(summary) is True


@pytest.mark.parametrize(
    "summary",
    [
        "The patient reports sleeping badly and low energy this week.",
        "The patient says they feel depressed since starting work.",
        "Patient described feeling depressed after the exam results.",
        "The patient reports stress about deadlines and arguments at home.",
        "Nothing concerning was reported by the patient.",
    ],
)
def test_descriptive_summaries_are_allowed(summary: str) -> None:
    assert contains_diagnostic_language(summary) is False


# --- evidence check ---------------------------------------------------------------


def test_exact_substring_evidence_is_kept() -> None:
    quote = "sleep badly"
    evidence, changed = validate_evidence(quote, TRANSCRIPT)
    assert evidence == quote
    assert changed is False


def test_paraphrased_evidence_is_rejected() -> None:
    evidence, changed = validate_evidence("I sleep poorly", TRANSCRIPT)
    assert evidence is None
    assert changed is True


def test_case_difference_is_rejected_as_not_exact() -> None:
    evidence, changed = validate_evidence("Sleep Badly", TRANSCRIPT)
    assert (evidence, changed) == (None, True)


def test_null_evidence_passes_through_unchanged() -> None:
    assert validate_evidence(None, TRANSCRIPT) == (None, False)


def test_blank_evidence_is_dropped_but_not_flagged_as_rejected_quote() -> None:
    evidence, changed = validate_evidence("   ", TRANSCRIPT)
    assert evidence is None
    assert changed is False


# --- schemas ----------------------------------------------------------------------


def test_higher_risk_picks_the_severity_and_ignores_none() -> None:
    assert higher_risk("low", "high") == "high"
    assert higher_risk("high", "moderate") == "high"
    assert higher_risk("moderate", "low") == "moderate"
    assert higher_risk(None, "low") == "low"
    assert higher_risk(None, None) is None


def test_outcome_crisis_visibility() -> None:
    assert AnalysisOutcome.crisis_visible("moderate") is True
    assert AnalysisOutcome.crisis_visible("high") is True
    assert AnalysisOutcome.crisis_visible("low") is False


def test_analysis_is_typed_and_strict_about_risk() -> None:
    analysis = Analysis.model_validate(VALID)
    assert analysis.symptoms.energy == 3
    with pytest.raises(ValueError):
        Analysis.model_validate({**VALID, "risk_level": "extreme"})
