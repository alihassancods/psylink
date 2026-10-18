"""Validation and safety checks applied to whatever the LLM returns.

Nothing here calls the model: each function is pure, so the pipeline's guarantees
(evidence must be quotable, summaries must not diagnose) hold regardless of prompt or
provider behaviour.
"""

import json
import re

from app.services.analysis.schemas import Analysis

#: Words that turn a neutral summary into a diagnosis. Matched case-insensitively as
#: substrings on the normalised summary, so "has Depression" and "HAS DEPRESSION" both hit.
DIAGNOSTIC_TERMS: tuple[str, ...] = (
    "has depression",
    "had depression",
    "is depressed",
    "clinical depression",
    "depressed",
    "depression",
    "bipolar",
    "disorder",
    "diagnos",
    "ptsd",
    "anxiety disorder",
    "psychosis",
    "psychotic",
    "manic",
    "dementia",
    "schizo",
    "ocd",
    "personality disorder",
    "eating disorder",
    "clinical",
    "pathological",
)

# "depression" is banned, but "feels depressed" is the patient's own word; that descriptive
# form is allowed back in because it reports rather than labels.
_ALLOWED_DIAGNOSTIC_CONTEXT = re.compile(
    r"\b(?:the\s+)?(?:patient|user|person)\b[^.]{0,25}"
    r"(?:says?|said|say\w*|feel\w*|describ\w*|report\w*|sound\w*|mention\w*|not\w*)"
    r"[^.]{0,30}\bdepress\w*\b"
    r"|\b(?:feels?|felt|feeling|described\s+as|says\s+they\s+(?:are|feel)|reports?\s+"
    r"(?:feeling|being))\s+depressed\b"
)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def normalise_for_terms(text: str) -> str:
    """Lowercase and collapse non-alphanumerics so blocklist matching is robust."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def contains_diagnostic_language(summary: str) -> bool:
    """True when the summary uses a clinical label the model has no business applying."""
    folded = normalise_for_terms(summary)
    for term in DIAGNOSTIC_TERMS:
        if term not in folded:
            continue
        # Only the "depress*" family is conditionally allowed back in its descriptive form.
        if term in {"depressed", "depression"} and _ALLOWED_DIAGNOSTIC_CONTEXT.search(folded):
            continue
        return True
    return False


def validate_evidence(evidence: str | None, transcript: str) -> tuple[str | None, bool]:
    """Keep ``evidence`` only if it is an exact substring of the transcript.

    Returns ``(evidence_or_None, changed)``; ``changed`` is True when a non-null quote was
    rejected, which is the signal to downgrade confidence to "low".
    """
    if evidence is None:
        return None, False
    if evidence and evidence in transcript:
        return evidence, False
    return None, evidence.strip() != ""


def _balanced_object(text: str) -> str | None:
    """Return the first complete ``{...}`` run, so stray prose around it does not break us."""
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start : index + 1]
            if depth < 0:
                depth = 0
    return None


def parse_analysis(raw: str) -> Analysis:
    """Parse a model reply into ``Analysis``.

    Accepts fenced markdown, or an object wrapped in stray prose. Raises ``ValueError`` for
    anything that is not one valid, schema-conforming JSON object; the pipeline turns that
    into its single stricter retry.
    """
    text = _FENCE.sub("", raw or "").strip()
    candidate = text
    if not text.startswith("{"):
        found = _balanced_object(text)
        if found is None:
            raise ValueError("no json object in response")
        candidate = found
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("json root must be an object")
    return Analysis.model_validate(data)
