"""Deterministic high-risk keyword screen — the floor the LLM can never lower.

Deliberately conservative: it only reports ``"high"`` or nothing, never grades down.
Ambiguous phrasing is flagged, because a missed suicide mention costs far more than an
extra alert. Negation ("I'm not thinking of hurting myself") and idioms ("this exam is
killing me") are suppressed so the floor stays credible; risk-bearing double negatives
("I don't want to live", "no reason to live") are immune to negation suppression.

Matching runs on a normalised copy: lowercased, curly quotes and dashes folded to ASCII,
runs of other characters collapsed. Comma/period-style punctuation is kept so clause
structure survives — a negation only suppresses a trigger inside its *own* clause, so
"I'm not scared of anything, I want to die" still fires.

Pattern syntax: ``{g}`` is a required gap (space and/or punctuation), ``{G}`` an optional
one, so "kill{G}my{g}self" covers "kill myself", "killing myself" and "kill, my self!".
"""

import re
from typing import Final, Literal

NEGATION_WINDOW: Final = 30
IDIOM_WINDOW: Final = 30

Trigger = tuple[re.Pattern[str], bool]  # (pattern, negation_immune)

_GAP = r"[\s.,;:!?\-']+"
_OPT_GAP = r"[\s.,;:!?\-']*"
# A negation only governs its own clause: punctuation and conjunctions both end its reach,
# so "I'm not sleeping and I want to die" keeps the risk statement un-negated.
_CLAUSE_BREAK = re.compile(
    r"[.;:!?,]|\b(?:and|but|so|yet|or|although|though|because|since|while|then|however|"
    r"also|when|whenever|if|after|before|until|plus|anyway|instead|meanwhile)\b"
)


def _compile(pattern: str) -> re.Pattern[str]:
    """Build a case-insensitive verbose regex, expanding the {g}/{G} gap sentinels."""
    expanded = pattern.replace("{G}", _OPT_GAP).replace("{g}", _GAP)
    return re.compile(expanded, re.IGNORECASE | re.VERBOSE)


# --- High-risk families ---------------------------------------------------------------------
# ``True`` marks a pattern whose own negation IS the risk signal, skipping the negation check.
SUICIDAL: Final[list[Trigger]] = [
    (_compile(r"kill(?:ing|ed|s)? {G}my {G}self"), False),
    (_compile(r"kill(?:ing|ed|s)? {g}me\b"), False),
    (_compile(r"end(?:ing)? {g}(?:my|ur) {g}life"), False),
    (_compile(r"end(?:ing)? {g}it {g}all"), False),
    (_compile(r"take {G}my {G}own {G}(?:life|breath)"), False),
    # "suicide"/"suicidal" plus common misspellings, kept narrow so "suit"/"separate" miss.
    (_compile(r"\bsui(?:c|d)\w* | \bsua(?:c|d)\w* | \bsuiac\w* | \bsuicid\w*"), False),
    (
        _compile(
            r"(?:want|wanna|plann?ing|plan|mean)(?:s|ed|ing)? {g}to {g}(?:die|be {g}dead|"
            r"cease {g}to {g}exist|drop {g}dead)"
        ),
        False,
    ),
    (_compile(r"(?:dying|dead) {g}inside"), False),
    (_compile(r"(?:i'?m|i {g}am|we'?re) {g}dying\b"), False),
    (
        _compile(
            r"wish(?:ed)? {g}i {g}(?:was|were|had {g}never|never {g}was) "
            r"{g}(?:dead|been {g}dead|never {g}born|existed)"
        ),
        False,
    ),
    (_compile(r"better {g}off {g}dead"), False),
    # Passive ideation: preferring non-existence, wishing to be gone.
    (_compile(r"(?:i'?d|would|we'?re) {g}rather {g}be {g}(?:dead|gone|not {g}here)"), False),
    (_compile(r"(?:i'?m|im) {g}(?:glad|sorry|happier) {g}(?:dead|gone)"), False),
    (
        _compile(
            r"wish {g}i {g}(?:wasn'?t|weren'?t|was {g}not|were {g}not) {g}(?:here|alive|"
            r"born|existing)"
        ),
        False,
    ),
    (
        _compile(
            r"(?:going {g}to|planned? {g}to|planning {g}to|intend(?:s|ed)? {g}to|"
            r"thinking {g}about|considering) {g}(?:killing|kill|die|dying|ending)"
        ),
        False,
    ),
    (_compile(r"suicide {g}(?:note|method|methods|pills?|plan|attempt|urge|thoughts?)"), False),
    # Negation-immune: the negation is the content.
    (
        _compile(
            r"(?:don'?t|does {g}not|do {g}not|didn'?t|can'?t|cannot|won'?t|would {g}not|"
            r"never|not) {g}want {g}to {g}(?:live|be {g}alive|be {g}here|go {g}on|"
            r"exist|wake {g}up|survive)"
        ),
        True,
    ),
    (
        _compile(
            r"(?:don'?t|doesn'?t|do {g}not|no) {g}(?:want|need|reason) {g}to {g}(?:live|go {g}on|"
            r"being? {g}here|exist)"
        ),
        True,
    ),
    (
        _compile(
            r"no {G}(?:reason|point|purpose|meaning|way) {g}to {g}(?:live|be {g}here|"
            r"go {g}on|going {g}on|keep {g}living|exist)"
        ),
        True,
    ),
    (
        _compile(
            r"(?:too|way {g}too) {g}(?:tired|sad|low|much) {g}to {g}(?:live|go {g}on|"
            r"keep {g}living|stay)"
        ),
        True,
    ),
    (_compile(r"not {g}sure {g}i {g}want {g}to {g}(?:live|be {g}here|go {g}on)"), True),
]

# Self-harm.
SELF_HARM: Final[list[Trigger]] = [
    (
        _compile(
            r"(?:hurt|harm|burn|hit|beat|scratch|slap|punch|chop|injure)(?:ing|s|ed)? "
            r"{G}my {G}self | cut(?:ting|s)? {G}my {G}self"
        ),
        False,
    ),
    (_compile(r"self {G}harm\w*"), False),
    (_compile(r"over\s?dos\w*"), False),
    (
        _compile(
            r"swallow(?:ed|ing|s)? {g}(?:all {G}the {g})?(?:pills?|tablets?|"
            r"medication|medicine|them {g}all)"
        ),
        False,
    ),
    (_compile(r"(?:stop|can'?t {g}stop|keep) {g}cutting {G}myself"), False),
]

# Risk of harming others.
HARMING_OTHERS: Final[list[Trigger]] = [
    (
        _compile(
            r"kill(?:ing|ed|s)? {g}(?:someone|somebody|him|her|them|people|others|"
            r"everybody|everyone|a {g}person|my {g}(?:family|kids?|children|son|daughter|"
            r"mother|father|wife|husband|ex|roommate|sibling|brother|sister))"
        ),
        False,
    ),
    (
        _compile(
            r"(?:hurt|harm|attack|poison|kill)(?:s|ing|ed)? {g}(?:someone|somebody|him|her|"
            r"them|people|others|my {g}(?:family|kids?|children|son|daughter|mother|father|"
            r"wife|husband|ex|roommate|sibling|brother|sister))"
        ),
        False,
    ),
    (
        _compile(
            r"(?:going {g}to|planned? {g}to|planning {g}to|intend(?:s|ed)? {g}to) {g}"
            r"(?:hurt|harm|attack|poison)"
        ),
        False,
    ),
]

TRIGGERS: Final[list[Trigger]] = [*SUICIDAL, *SELF_HARM, *HARMING_OTHERS]

# --- Idiomatic readings of otherwise-triggering phrases ---------------------------------------
IDIOMS: Final[list[re.Pattern[str]]] = [
    _compile(r"(?:is|was|were|'s|'ll) {g}killing {g}(?:me|us)\b"),
    _compile(r"this [a-z]+ {g}is {g}killing {g}me"),
    _compile(r"killing {g}it\b"),
    _compile(
        r"kill(?:s|ing)? {g}the {g}(?:time|day|night|moment|ballpark|two {g}birds|"
        r"rope|light|lights)"
    ),
    _compile(r"(?:would|will|gonna|going {g}to) {g}die {g}for"),
    _compile(
        r"dying {g}(?:to|for|of) {g}(?:a|an|the|some|my)? {G}(?:see|meet|have|get|try|"
        r"know|go|coffee|cake|pizza|chocolate|nap|sleep|vacation|holiday|weekend|"
        r"laughter|boredom|embarrassment|first)"
    ),
    _compile(
        r"(?:scared|bored|worked|starved|tired|exhausted|beat|busted|worn|jumped|"
        r"screamed|laughed) {g}to {g}death"
    ),
    _compile(r"death {g}of {g}(?:me|us)"),
    _compile(
        r"(?:exam|test|interview|deadline|work|study|class|homework|thesis|paper|shift|"
        r"holiday|shopping|travel|flight|journey|queue|heat|cold|weather|noise|traffic|"
        r"smoke|humidity|run|gym|exercise|meeting|movie|joke|game)\w* [a-z ]{{0,20}} "
        r"{g}to {g}death"
    ),
]

# Cues that cancel a trigger when they govern the same clause. Bare "no"/"over"/"done" are
# left out: they show up in too many unrelated windows.
NEGATION_CUES: Final[re.Pattern[str]] = _compile(
    r"\b(?:not|never|neither|nor|without|hardly|barely|avoid(?:ed|ing)?|"
    r"refus(?:e|ed|es|ing)|stop(?:s|ped|ping)|quit|ceased)\b | \bn't\b"
)

_REPLACEMENTS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile("[\u2018\u2019\u201c\u201d]"), "'"),
    (re.compile("[\u2013\u2014]"), "-"),
    (re.compile(r"[^a-z0-9'.,;:!?\-]+"), " "),
]


def normalise(text: str) -> str:
    """Lowercase, fold typographic marks, collapse junk runs; keep clause punctuation."""
    folded = text.lower()
    for pattern, replacement in _REPLACEMENTS:
        folded = pattern.sub(replacement, folded)
    return re.sub(r"\s+", " ", folded).strip()


def _before_clause(text: str, start: int) -> str:
    """The words just before the trigger, cut off at the nearest clause boundary.

    Boundaries are punctuation *and* conjunctions: without the latter, "I'm not sleeping
    and I want to die" would let "not" suppress a separate risk statement two clauses away.
    """
    boundary = 0
    for match in _CLAUSE_BREAK.finditer(text[:start]):
        boundary = match.end()
    return text[boundary:start][-NEGATION_WINDOW:]


def _overlaps_idiom(text: str, start: int, end: int) -> bool:
    window_start = max(0, start - IDIOM_WINDOW)
    window_end = min(len(text), end + IDIOM_WINDOW)
    window = text[window_start:window_end]
    return any(idiom.search(window) for idiom in IDIOMS)


def _negated_in_clause(text: str, start: int) -> bool:
    return bool(NEGATION_CUES.search(_before_clause(text, start)))


def screen_text(text: str) -> bool:
    """Does this text contain non-negated, non-idiomatic high-risk content?"""
    normalised = normalise(text)
    if not normalised:
        return False
    for pattern, negation_immune in TRIGGERS:
        for match in pattern.finditer(normalised):
            if _overlaps_idiom(normalised, match.start(), match.end()):
                continue
            if not negation_immune and _negated_in_clause(normalised, match.start()):
                continue
            return True
    return False


def screen(transcript: str) -> Literal["high"] | None:
    """The pipeline floor: ``"high"`` when the screen fires, otherwise ``None``."""
    return "high" if screen_text(transcript) else None
