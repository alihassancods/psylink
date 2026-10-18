"""Synthetic demo data: one clinician, three patients, fourteen days of check-ins.

Everything here is **invented for the demo**. The sentences are written to exercise the pipeline
shape — mood, symptoms, and one deliberately keyword-triggering crisis entry — not to imitate a
real person's words. Nothing in this module is derived from any actual patient, and the same
rule applies to the screenshots and the demo script.

Two properties are deliberate:

* **Idempotent.** `seed_demo()` deletes what it previously wrote (matched by the demo emails) and
  reinserts, so running it before every recording leaves the same dashboard, not a growing one.
  The cascade from `profiles` takes consents, check-ins, analyses and alerts with it.
* **Written through `service_client()`.** Demo analyses must land in `analyses`, a table
  `authenticated` cannot write — that is the whole point of the tamper-proofing, so the seeder
  uses the same door the pipeline uses rather than pretending to be a patient.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.db import service_client

#: Demo accounts. The local part is what `find_or_create` matches on.
DEMO_CLINICIAN_EMAIL = "demo.clinician@bridge.example"
DEMO_PATIENT_EMAILS = (
    "demo.patient.stable@bridge.example",
    "demo.patient.deteriorating@bridge.example",
    "demo.patient.crisis@bridge.example",
)
DEMO_NAMESPACE = uuid.UUID("2f7a5a67-8b0e-4f6b-9d3c-0a1b2c3d4e5f")

DEMO_PASSWORD_NOTE = "created through the Supabase dashboard or --create-auth-users"


@dataclass(frozen=True)
class DemoUser:
    email: str
    display_name: str
    role: str

    @property
    def id(self) -> uuid.UUID:
        """A stable id derived from the email, so re-seeding lines up with existing auth users."""
        return uuid.uuid5(DEMO_NAMESPACE, self.email)


@dataclass(frozen=True)
class UserCredential:
    """What to type into the login screen. Passwords are supplied by whoever made the users."""

    email: str
    display_name: str
    role: str


CLINICIAN = DemoUser(DEMO_CLINICIAN_EMAIL, "Dr Amara Osei", "clinician")
PATIENTS = (
    DemoUser(DEMO_PATIENT_EMAILS[0], "Sam Rivera", "patient"),
    DemoUser(DEMO_PATIENT_EMAILS[1], "Priya Nair", "patient"),
    DemoUser(DEMO_PATIENT_EMAILS[2], "Jonah Weiss", "patient"),
)


# --- the synthetic narratives ---------------------------------------------------------
# Each tuple is (day offset, mood 1-10, transcript). Offsets count back from "today".

DEMO_USERS: tuple[DemoUser, ...] = (CLINICIAN, *PATIENTS)


STABLE: tuple[tuple[int, int, str], ...] = (
    (13, 7, "Sleeping okay this week, coursework is busy but manageable."),
    (10, 8, "Fine mostly. Went for a run twice and ate properly."),
    (7, 7, "A bit tired before the seminar but nothing worrying."),
    (4, 8, "Good week. Saw friends at the weekend."),
    (1, 7, "Steady. Sleeping about seven hours."),
)

DETERIORATING: tuple[tuple[int, int, str], ...] = (
    (13, 6, "Sleeping badly, waking at three and can't get back down."),
    (11, 5, "No appetite again. Skipping meals most days."),
    (9, 5, "Tired all day and snapping at people for no reason."),
    (7, 4, "Stopped answering messages from my family. Prefer being on my own."),
    (5, 3, "Can't concentrate on anything, reading the same page for an hour."),
    (3, 3, "Everything feels heavy and I can't see the point of the next month."),
    (1, 2, "I don't think I can keep going like this, honestly."),
)

#: The final entry contains words the keyword screen is built to catch — that is the point of
#: having a crisis patient in the demo: it exercises the alert path end to end.
CRISIS: tuple[tuple[int, int, str], ...] = (
    (12, 5, "Rough week but holding it together."),
    (8, 4, "Not sleeping again, crying most nights."),
    (5, 3, "Feeling hopeless about everything since the deadline passed."),
    (2, 2, "I keep thinking everyone would be better off without me."),
    (0, 1, "I want to kill myself and I have thought about how."),
)

NARRATIVES: dict[str, tuple[tuple[int, int, str], ...]] = {
    PATIENTS[0].email: STABLE,
    PATIENTS[1].email: DETERIORATING,
    PATIENTS[2].email: CRISIS,
}

SYMPTOM_NAMES = (
    "sleep",
    "appetite",
    "energy",
    "anxiety",
    "concentration",
    "social_withdrawal",
    "irritability",
)


def _symptoms_for(mood: int, transcript: str) -> dict[str, int | None]:
    """Cheap synthetic symptom scores: worse mood raises them, and mention beats inference."""
    lowered = transcript.lower()
    base = 0 if mood >= 7 else 1 if mood >= 5 else 2 if mood >= 3 else 3
    mentions = {
        "sleep": ("sleep", "waking", "nights"),
        "appetite": ("appetite", "meals", "eat"),
        "energy": ("tired", "heavy"),
        "concentration": ("concentrate", "same page"),
        "social_withdrawal": ("messages", "on my own", "friends"),
        "irritability": ("snapping",),
        "anxiety": ("deadline", "worried"),
    }
    out: dict[str, int | None] = {}
    for name in SYMPTOM_NAMES:
        mentioned = any(word in lowered for word in mentions[name])
        out[name] = min(3, base + (1 if mentioned else 0)) if mentioned or base >= 2 else None
    return out


def _risk_for(mood: int, transcript: str) -> str:
    """Deterministic, matching what the pipeline's own screen would conclude."""
    from app.services.analysis.keywords import screen

    lowered = transcript.lower()
    if screen(transcript) == "high":
        return "high"
    if mood <= 3 or "hopeless" in lowered or "better off without me" in lowered:
        return "moderate"
    return "low"


def _summary_for(transcript: str, mood: int) -> str:
    return f"The patient reports feeling about {mood} out of 10 and says: {transcript[:120]}"


def _evidence_for(transcript: str, risk: str) -> str | None:
    """An exact substring of the transcript, because that is what the guardrail requires."""
    if risk == "low":
        return None
    for phrase in (
        "I want to kill myself",
        "better off without me",
        "can't keep going like this",
        "can't see the point",
        "hopeless",
    ):
        if phrase.lower() in transcript.lower():
            start = transcript.lower().index(phrase.lower())
            return transcript[start : start + len(phrase)]
    return None


def build_entries(email: str, *, today: datetime | None = None) -> list[dict[str, Any]]:
    """Synthetic check-in rows for one demo patient, oldest first."""
    anchor = today or datetime.now(UTC)
    entries = []
    for offset, mood, transcript in sorted(NARRATIVES[email], key=lambda e: e[0], reverse=True):
        risk = _risk_for(mood, transcript)
        created = anchor - timedelta(days=offset, hours=1)
        entries.append(
            {
                "created_at": created,
                "transcript": transcript,
                "analysis": {
                    "mood_score": mood,
                    "emotions": _emotions_for(mood),
                    "symptoms": _symptoms_for(mood, transcript),
                    "risk_level": risk,
                    "risk_evidence": _evidence_for(transcript, risk),
                    "confidence": "high" if mood >= 7 else "medium",
                    "risk_source": "keyword" if risk == "high" else "llm",
                },
                "summary": _summary_for(transcript, mood),
            }
        )
    return entries


def _emotions_for(mood: int) -> list[str]:
    if mood >= 7:
        return ["okay", "steady"]
    if mood >= 5:
        return ["tired", "stressed"]
    if mood >= 3:
        return ["sad", "hopeless", "exhausted"]
    return ["despairing", "alone", "exhausted"]


#: `analyses.risk` is the schema enum; the app calls "moderate" that, and the DB "medium".
DB_RISK: dict[str, str] = {"low": "low", "moderate": "medium", "high": "high"}


async def purge_demo() -> None:
    """Remove the previous demo dataset. Cascades take children with them."""
    ids = [user.id for user in (CLINICIAN, *PATIENTS)]
    async with service_client() as db:
        await db.execute(
            "delete from public.profiles where id = any(cast(:ids as uuid[]))",
            ids=[str(i) for i in ids],
        )


async def seed_demo(
    *, today: datetime | None = None, raise_demo_alerts: bool = True
) -> dict[str, Any]:
    """Write the demo dataset and report what it contains.

    `raise_demo_alerts` seeds an open alert for the crisis patient so the clinician inbox is not
    empty during a demo. It is fake traffic on fake data — the real alert path is exercised by
    `tests/test_alerts.py` and by filing a check-in.
    """
    await purge_demo()
    anchor = today or datetime.now(UTC)
    counts = {"profiles": 0, "consents": 0, "checkins": 0, "analyses": 0, "alerts": 0}

    async with service_client() as db:
        for person in (CLINICIAN, *PATIENTS):
            await db.insert(
                "profiles",
                {
                    "id": str(person.id),
                    "role": person.role,
                    "display_name": person.display_name,
                    "email": person.email,
                },
            )
            counts["profiles"] += 1

        for patient in PATIENTS:
            await db.insert(
                "consents",
                {
                    "patient_id": str(patient.id),
                    "clinician_id": str(CLINICIAN.id),
                    "granted_at": anchor - timedelta(days=20),
                },
            )
            counts["consents"] += 1

        for patient in PATIENTS:
            last_analysis_id: str | None = None
            for entry in build_entries(patient.email, today=anchor):
                checkin = await db.insert(
                    "checkins",
                    {
                        "patient_id": str(patient.id),
                        "created_at": entry["created_at"],
                        "transcript": entry["transcript"],
                        "answers": {"source": "typed"},
                        "analysis_status": "analyzed",
                    },
                )
                analysis = await db.insert(
                    "analyses",
                    {
                        "patient_id": str(patient.id),
                        "checkin_id": str(checkin["id"]),
                        "created_at": entry["created_at"],
                        "model": "demo-synthetic",
                        "summary": entry["summary"],
                        "risk": DB_RISK[entry["analysis"]["risk_level"]],
                        "signals": entry["analysis"],
                    },
                )
                counts["checkins"] += 1
                counts["analyses"] += 1
                last_analysis_id = str(analysis["id"])

            if raise_demo_alerts and patient is PATIENTS[2] and last_analysis_id:
                await db.insert(
                    "alerts",
                    {
                        "patient_id": str(patient.id),
                        "clinician_id": str(CLINICIAN.id),
                        "analysis_id": last_analysis_id,
                        "severity": "high",
                        "message": "High-risk check-in needs review",
                    },
                )
                counts["alerts"] += 1

    return {
        "counts": counts,
        "clinician": {"email": CLINICIAN.email, "id": str(CLINICIAN.id)},
        "patients": [{"email": p.email, "id": str(p.id), "name": p.display_name} for p in PATIENTS],
        "note": (
            f"Synthetic demo data only. Logins must exist in Supabase auth ({DEMO_PASSWORD_NOTE})."
        ),
    }


def fingerprint(email: str) -> str:
    """Short stable handle for a demo account, used in printed credentials."""
    return hashlib.sha256(email.encode()).hexdigest()[:8]
