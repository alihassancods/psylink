"""Fixtures for the row-level-security suite.

Two rules shape this file, and both come straight from how the policies under test work:

* Seeding goes through ``service_client()`` in its **own committed transaction**. A reader in a
  different transaction — every ``user_client`` — cannot see uncommitted rows, so these fixtures
  write and return instead of handing out one long-lived client.
* Every seeded row hangs off a `profiles` row, and those cascades, so teardown is a single delete
  however many check-ins, analyses, alerts, or consents a test created.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.services.db import Row, service_client

#: (table, values) -> the inserted row, written as the service identity.
InsertRow = Callable[[str, Mapping[str, Any]], Awaitable[Row]]

PEOPLE: dict[str, int] = {
    "patient_a": 0x0A0A0A0A_0000_4000_8000_000000000001,
    "patient_b": 0x0B0B0B0B_0000_4000_8000_000000000002,
    "clinician": 0x0C0C0C0C_0000_4000_8000_000000000003,
    "other_clinician": 0x0D0D0D0D_0000_4000_8000_000000000004,
    "stranger": 0x0E0E0E0E_0000_4000_8000_000000000005,
}


async def _delete_people(client: Any, ids: list[UUID]) -> None:
    await client.execute(
        "delete from public.profiles where id = any(cast(:ids as uuid[]))", ids=ids
    )


@pytest.fixture
async def people() -> AsyncIterator[dict[str, UUID]]:
    """Two patients, two clinicians, and one identity with no profile row at all."""
    ids = {name: UUID(int=value) for name, value in PEOPLE.items()}

    async with service_client() as client:
        # Clear leftovers first: a crashed run would otherwise collide with these fixed ids.
        await _delete_people(client, list(ids.values()))
        await client.insert(
            "profiles", {"id": ids["patient_a"], "role": "patient", "display_name": "Patient A"}
        )
        await client.insert(
            "profiles", {"id": ids["patient_b"], "role": "patient", "display_name": "Patient B"}
        )
        await client.insert(
            "profiles", {"id": ids["clinician"], "role": "clinician", "display_name": "Dr Who"}
        )
        await client.insert(
            "profiles",
            {"id": ids["other_clinician"], "role": "clinician", "display_name": "Dr Other"},
        )

    yield ids

    async with service_client() as client:
        await _delete_people(client, list(ids.values()))


@pytest.fixture
async def insert_row() -> AsyncIterator[InsertRow]:
    """Insert one row as the service role and commit it immediately, so readers can see it."""

    async def factory(table: str, values: Mapping[str, Any]) -> Row:
        async with service_client() as client:
            row = await client.insert(table, values)
        assert row is not None, f"service_client lost the inserted {table} row"
        return row

    yield factory


@pytest.fixture
def consent(people: dict[str, UUID], insert_row: InsertRow) -> Callable[..., Awaitable[Row]]:
    """Link a clinician to a patient; pass revoked_at to plant an already-revoked grant."""

    async def factory(
        patient_id: UUID | None = None,
        clinician_id: UUID | None = None,
        *,
        revoked_at: datetime | None = None,
    ) -> Row:
        return await insert_row(
            "consents",
            {
                "patient_id": patient_id or people["patient_a"],
                "clinician_id": clinician_id or people["clinician"],
                "revoked_at": revoked_at,
            },
        )

    return factory


@pytest.fixture
async def checkin_of_a(people: dict[str, UUID], insert_row: InsertRow) -> Row:
    """Patient A's check-in, with a nested answer so jsonb round-tripping is exercised too."""
    return await insert_row(
        "checkins",
        {
            "patient_id": people["patient_a"],
            "answers": {"mood": 3, "pain": 7, "notes": "tired"},
            "note": "felt awful this morning",
        },
    )


@pytest.fixture
async def analysis_of_a(people: dict[str, UUID], insert_row: InsertRow, checkin_of_a: Row) -> Row:
    return await insert_row(
        "analyses",
        {
            "patient_id": people["patient_a"],
            "checkin_id": checkin_of_a["id"],
            "model": "demo-model",
            "summary": "Pain trending up over three days.",
            "risk": "high",
            "signals": {"pain_slope": 1.4},
        },
    )


@pytest.fixture
async def alert_for_a(people: dict[str, UUID], insert_row: InsertRow, analysis_of_a: Row) -> Row:
    return await insert_row(
        "alerts",
        {
            "patient_id": people["patient_a"],
            "clinician_id": people["clinician"],
            "analysis_id": analysis_of_a["id"],
            "severity": "high",
            "message": "Patient A risk escalated to high.",
        },
    )


@pytest.fixture
async def checkin_of_b(people: dict[str, UUID], insert_row: InsertRow) -> Row:
    return await insert_row(
        "checkins",
        {"patient_id": people["patient_b"], "answers": {"mood": 5}, "note": "patient B private"},
    )


@pytest.fixture
async def analysis_of_b(people: dict[str, UUID], insert_row: InsertRow, checkin_of_b: Row) -> Row:
    return await insert_row(
        "analyses",
        {
            "patient_id": people["patient_b"],
            "checkin_id": checkin_of_b["id"],
            "summary": "B is stable.",
            "risk": "low",
        },
    )


@pytest.fixture
async def alert_for_b(people: dict[str, UUID], insert_row: InsertRow, analysis_of_b: Row) -> Row:
    return await insert_row(
        "alerts",
        {
            "patient_id": people["patient_b"],
            "clinician_id": people["clinician"],
            "analysis_id": analysis_of_b["id"],
            "message": "B escalated.",
            "severity": "high",
        },
    )


def utc_now() -> datetime:
    """Naive-free `now`, matching what the timestamp columns hold."""
    return datetime.now(UTC)
