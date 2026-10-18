"""1.13 demo data: it is synthetic, deterministic, idempotent, and readable through the API.

The seeder writes through `service_client()`, so these tests run against the real database the
suite is pinned to — the same code path a live `seed_demo.py` takes.
"""

import re
from datetime import UTC, datetime

import pytest

from app.services.analysis.keywords import screen
from app.services.db import service_client
from app.services.demo_seed import (
    CLINICIAN,
    CRISIS,
    DEMO_USERS,
    PATIENTS,
    build_entries,
    fingerprint,
    purge_demo,
    seed_demo,
)


@pytest.fixture(autouse=True)
async def _clean_demo_rows():
    await purge_demo()
    yield
    await purge_demo()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- shape of the dataset -----------------------------------------------------------


def test_demo_ids_are_stable_and_unique() -> None:
    ids = {user.id for user in DEMO_USERS}
    assert len(ids) == 4
    # Derived from the email, so re-running the seeder lines up with existing auth users.
    assert CLINICIAN.id != PATIENTS[0].id
    from app.services.demo_seed import DemoUser

    assert DemoUser("x@y.z", "X", "patient").id == DemoUser("x@y.z", "Other", "patient").id


def test_every_narrative_is_dated_within_two_weeks() -> None:
    now = datetime.now(UTC)
    for patient in PATIENTS:
        for entry in build_entries(patient.email):
            assert entry["created_at"] <= now
            assert (now - entry["created_at"]).days <= 14


def test_crisis_patient_actually_triggers_the_keyword_floor() -> None:
    """The demo's alert path is only a demo if the screen really fires on it."""
    assert screen(CRISIS[-1][2]) == "high"
    entries = build_entries(PATIENTS[2].email)
    assert entries[-1]["analysis"]["risk_level"] == "high"
    assert entries[-1]["analysis"]["risk_source"] == "keyword"


def test_deteriorating_patient_trends_downward() -> None:
    moods = [e["analysis"]["mood_score"] for e in build_entries(PATIENTS[1].email)]
    assert moods == sorted(moods, reverse=True)  # worst number last
    assert moods[0] > moods[-1]
    assert moods[-1] <= 3


def test_stable_patient_never_reads_as_a_crisis() -> None:
    entries = build_entries(PATIENTS[0].email)
    assert all(e["analysis"]["risk_level"] == "low" for e in entries)
    assert all(e["analysis"]["risk_evidence"] is None for e in entries)


def test_evidence_quotes_are_exact_substrings_of_their_transcript() -> None:
    """The guardrail the pipeline enforces is enforced on demo data too."""
    for patient in PATIENTS:
        for entry in build_entries(patient.email):
            quote = entry["analysis"]["risk_evidence"]
            if quote:
                assert quote in entry["transcript"]


def test_no_demo_text_is_real_clinical_content_or_pii() -> None:
    # Names are invented, domains are the reserved example ones, and no phone/address data.
    for user in DEMO_USERS:
        assert user.email.endswith("@bridge.example")
    assert all(not re.search(r"\b\d{3}[-.]\d{4}\b", t) for _, _, t in CRISIS)


def test_fingerprint_is_stable() -> None:
    assert fingerprint("a@b.c") == fingerprint("a@b.c")
    assert fingerprint("a@b.c") != fingerprint("d@e.f")


# --- seeding it ---------------------------------------------------------------------


async def test_seed_writes_the_expected_volume_once_and_again() -> None:
    first = await seed_demo()
    second = await seed_demo()  # idempotent: no growth
    assert first["counts"] == second["counts"]
    assert first["counts"]["profiles"] == 4
    assert first["counts"]["consents"] == 3
    assert first["counts"]["checkins"] == first["counts"]["analyses"] >= 15
    assert first["counts"]["alerts"] == 1

    # Scoped to the demo identities: the dev database is shared with every other suite, so a
    # global count would assert on whatever unrelated rows happen to exist.
    demo_ids = [str(u.id) for u in DEMO_USERS]
    placeholders = ", ".join(f":d{i}" for i in range(len(demo_ids)))
    params = {f"d{i}": v for i, v in enumerate(demo_ids)}
    async with service_client() as db:
        profiles = await db.scalar(
            f"select count(*) from public.profiles where id in ({placeholders})", **params
        )
        patients = [str(u.id) for u in PATIENTS]
        pph = ", ".join(f":p{i}" for i in range(len(patients)))
        pparams = {f"p{i}": v for i, v in enumerate(patients)}
        analyses = await db.scalar(
            f"select count(*) from public.analyses where patient_id in ({pph})", **pparams
        )
    assert profiles == 4
    assert analyses == first["counts"]["analyses"]


async def test_purge_leaves_no_demo_rows_behind() -> None:
    """Purging removes the demo dataset and everything that cascades from it.

    Asserted against the demo ids, not the whole schema: other suites legitimately leave rows
    in this shared database, and counting them here would make the test depend on run order.
    """
    await seed_demo()
    await purge_demo()
    ids = [str(u.id) for u in DEMO_USERS]
    ph = ", ".join(f":d{i}" for i in range(len(ids)))
    params = {f"d{i}": v for i, v in enumerate(ids)}
    async with service_client() as db:
        assert (
            await db.scalar(f"select count(*) from public.profiles where id in ({ph})", **params)
            == 0
        )
        for table, column in (
            ("consents", "patient_id"),
            ("consents", "clinician_id"),
            ("checkins", "patient_id"),
            ("analyses", "patient_id"),
            ("alerts", "patient_id"),
        ):
            left = await db.scalar(
                f"select count(*) from public.{table} where {column} in ({ph})", **params
            )
            assert left == 0, f"{table}.{column} still holds {left} demo rows"


async def test_risk_column_uses_the_schema_enum_not_the_app_wording() -> None:
    await seed_demo()
    async with service_client() as db:
        rows = await db.select("analyses", columns=("risk",))
    values = {row["risk"] for row in rows}
    assert values <= {"low", "medium", "high"}  # 'medium' is the schema's word for 'moderate'
    assert "moderate" not in values


# --- the API renders it -------------------------------------------------------------


async def test_clinician_roster_and_alerts_show_the_demo_dataset(api_client, make_token) -> None:
    await seed_demo()
    headers = bearer(make_token(CLINICIAN.id))

    roster = (await api_client.get("/api/patients", headers=headers)).json()
    assert roster["total"] == 3
    # The crisis patient is first because it has an open alert.
    assert roster["items"][0]["patient_id"] == str(PATIENTS[2].id)
    assert roster["items"][0]["open_alerts"] == 1
    assert roster["items"][0]["last_risk"] == "high"

    alerts = (await api_client.get("/api/alerts", headers=headers)).json()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "high"
    assert "kill" not in alerts[0]["message"].lower()


async def test_trend_of_the_deteriorating_patient_is_visible(api_client, make_token) -> None:
    await seed_demo()
    trend = (
        await api_client.get(
            f"/api/patients/{PATIENTS[1].id}/trend?days=14",
            headers=bearer(make_token(CLINICIAN.id)),
        )
    ).json()
    assert len(trend["points"]) == len(build_entries(PATIENTS[1].email))
    assert trend["points"][0]["mood_score"] < trend["points"][-1]["mood_score"]  # newest first


async def test_a_demo_patient_cannot_see_another_demo_patient(api_client, make_token) -> None:
    await seed_demo()
    victim, other = PATIENTS[0], PATIENTS[1]
    listed = (await api_client.get("/api/checkins", headers=bearer(make_token(victim.id)))).json()
    assert listed["items"], "demo patient should have check-ins to list"

    peek = await api_client.get(
        f"/api/patients/{other.id}/trend", headers=bearer(make_token(victim.id))
    )
    assert peek.status_code == 403  # that route is clinician-only


async def test_demo_checkin_detail_exposes_the_crisis_evidence(api_client, make_token) -> None:
    await seed_demo()
    crisis = PATIENTS[2]
    listed = (await api_client.get("/api/checkins", headers=bearer(make_token(crisis.id)))).json()
    newest = listed["items"][0]["checkin_id"]

    detail = (
        await api_client.get(
            f"/api/patients/{crisis.id}/checkins/{newest}",
            headers=bearer(make_token(CLINICIAN.id)),
        )
    ).json()
    assert detail["risk"] == "high"
    assert detail["evidence_quote"] and detail["evidence_quote"] in detail["transcript"]
    assert detail["model"] == "demo-synthetic"
