"""Keyword-screen cases: what must fire, what must stay quiet, and the floor guarantee."""

import pytest

from app.services.analysis.keywords import screen, screen_text

# Every one of these must produce "high".
POSITIVE_CASES = [
    "i want to kill myself",
    "I have been thinking about killing myself all week",
    "I keep thinking about suicide",
    "I'm suicidal",
    "I want to end my life",
    "I was thinking about ending it all",
    "Sometimes I wish I was dead",
    "I don't want to be here anymore, I want to die",
    "there is no reason to live",
    "everyone would be better off dead without me",
    "I planned to take my own life",
    "I'm going to kill myself tonight",
    "I have a suicide note written",
    "I've been looking up suicide methods",
    "I want to die",
    "i am dying inside",
    "I tried to over dose last night",
    "I have been hurting myself",
    "I've been cutting myself again",
    "self-harm has gotten worse",
    "I swallowed all the pills",
    "I want to kill my roommate",
    "I'm going to hurt someone at work",
    "sometimes I want to harm my family",
    # case, punctuation, spacing and typo variants
    "KILL MYSELF",
    "I want to KILL MYSELF right now",
    "i    want    to    die",
    "I want to, die, honestly.",
    "self\u2013harm is getting worse",  # en dash, folded to a space by normalise
    "i'm having \u201csuicial\u201d thoughts",  # curly quotes + typo
    "I keep having suacial thoughts",  # typo
    "I dont want to live anymore",
    # A negation in one clause must not silence a risk statement in the next.
    "I'm not sleeping and I want to kill myself",
    "I'm not angry, I want to die",
    "I have a job and a family but I want to end my life",
    "not much energy today, honestly I'd rather be dead",
]

# None of these should fire: negated, idiomatic, or simply unrelated.
NEGATIVE_CASES = [
    "I'm not thinking of hurting myself",
    "I'm not thinking about hurting myself anymore",
    "it's not that I want to die, I'm just exhausted",
    "I will never hurt myself, I promise",
    "I have not wanted to die since I started therapy",
    "it's not that I want to die",
    "this exam is killing me",
    "that film was killing me, I laughed so hard",
    "I'm killing it at the chess tournament",
    "let's kill the time with a board game",
    "I would die for a good night's sleep",
    "I'm dying for a coffee",
    "she is dying to see the results",
    "that joke scared me to death",
    "I'm bored to death on weekends",
    "the queue at the office worked me to death",
    "my roommate is on about the death of me again",
    "I have no intention to hurt anyone",
    "I stopped cutting myself months ago",
    "I would never want to hurt my family",
    "I feel sad, tired, and unmotivated most days",
    "work has been stressful and I sleep badly",
    "my cat died last week and I'm upset",
    "I had a nightmare about dying",
    "the doctor said this medication can cause drowsiness",
    "",
    "   ",
    "i am feeling great today",
]


@pytest.mark.parametrize("text", POSITIVE_CASES)
def test_high_risk_phrases_are_flagged(text: str) -> None:
    assert screen(text) == "high", text
    assert screen_text(text) is True


@pytest.mark.parametrize("text", NEGATIVE_CASES)
def test_negated_idiomatic_and_clean_text_is_not_flagged(text: str) -> None:
    assert screen(text) is None, text
    assert screen_text(text) is False


def test_screen_only_ever_returns_high_or_none() -> None:
    assert {screen(t) for t in POSITIVE_CASES + NEGATIVE_CASES} <= {"high", None}


def test_negation_does_not_erase_a_later_real_statement() -> None:
    """A negated clause must not suppress an unconditional statement in the same text."""
    assert screen("I'm not scared of anything, I want to die") == "high"


def test_double_negative_that_means_risk_still_fires() -> None:
    assert screen("I don't want to live anymore") == "high"
    assert screen("there's no point to going on") == "high"


def test_normalise_folds_typography_and_keeps_clause_punctuation() -> None:
    from app.services.analysis.keywords import normalise

    # Curly apostrophe -> ASCII, NBSP -> space, runs of junk -> single space. Clause
    # punctuation is deliberately kept so negation cannot leak across a comma.
    assert normalise("  Kill\u00a0My\u2019Self!! ") == "kill my'self!!"
    assert normalise("I'm not scared, I want to die") == "i'm not scared, i want to die"
    assert normalise(normalise("A   B.  C")) == "a b. c"


def test_case_insensitivity_is_not_just_lower() -> None:
    assert screen("I WANT TO END IT ALL") == "high"
    assert screen("i WaNt To eNd It AlL") == "high"
