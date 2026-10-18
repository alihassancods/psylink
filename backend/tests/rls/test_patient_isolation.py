"""Patients can read and write their own rows, and nothing belonging to anyone else.

Every denial asserted here comes from Postgres rather than a Python check: the same query a
compromised handler would run still returns nothing, because the row is not visible to the role
that the request assumed.
"""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError

from app.services.db import Row, service_client, user_client


async def _count(table: str) -> int:
    """How many rows a table holds, counted past RLS."""
    async with service_client() as client:
        return int(await client.scalar(f"select count(*) from public.{table}"))


async def test_patient_sees_only_their_own_checkins(
    people: dict[str, UUID],
    make_token: Any,
    checkin_of_a: Row,
    checkin_of_b: Row,
) -> None:
    assert await _count("checkins") == 2, "both check-ins exist; one is simply not A's"

    async with user_client(make_token(people["patient_a"])) as db:
        visible = await db.select("checkins")

    assert [row["id"] for row in visible] == [checkin_of_a["id"]]
    assert visible[0]["answers"] == {"mood": 3, "pain": 7, "notes": "tired"}, "jsonb round-trips"


async def test_patient_cannot_read_another_patients_profile(
    people: dict[str, UUID], make_token: Any
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        hidden = await db.select(
            "profiles", where="id = :other", params={"other": people["patient_b"]}
        )
        name = await db.scalar(
            "select display_name from profiles where id = :other", other=people["patient_b"]
        )
        mine = await db.select("profiles", where="id = :me", params={"me": people["patient_a"]})

    assert hidden == []
    assert name is None
    assert [row["display_name"] for row in mine] == ["Patient A"]


async def test_patient_cannot_read_another_patients_analysis_or_alert(
    people: dict[str, UUID],
    make_token: Any,
    analysis_of_a: Row,
    analysis_of_b: Row,
    alert_for_a: Row,
    alert_for_b: Row,
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        analyses = await db.select("analyses")
        alerts = await db.select("alerts")

    assert [row["id"] for row in analyses] == [analysis_of_a["id"]]
    assert [row["id"] for row in alerts] == [alert_for_a["id"]]


async def test_patient_cannot_write_checkins_for_someone_else(
    people: dict[str, UUID], make_token: Any, checkin_of_b: Row
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.insert("checkins", {"patient_id": people["patient_b"], "answers": {}})

    assert await _count("checkins") == 1


async def test_patient_cannot_change_or_delete_another_patients_checkin(
    people: dict[str, UUID], make_token: Any, checkin_of_b: Row
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        changed = await db.update(
            "checkins",
            {"note": "erased by someone else"},
            where="id = :id",
            params={"id": checkin_of_b["id"]},
        )
        deleted = await db.execute(
            "delete from public.checkins where id = :id", id=checkin_of_b["id"]
        )

    assert (changed, deleted) == (0, 0), "RLS hides the row, so it cannot be reached at all"

    async with service_client() as audit:
        stored = await audit.select(
            "checkins", columns=("note",), where="id = :id", params={"id": checkin_of_b["id"]}
        )
    assert stored[0]["note"] == "patient B private"


async def test_patient_writes_their_own_rows_freely(
    people: dict[str, UUID], make_token: Any, checkin_of_a: Row
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        created = await db.insert(
            "checkins",
            {"patient_id": people["patient_a"], "answers": {"mood": 1}, "note": "mine"},
        )
        assert created is not None and created["patient_id"] == people["patient_a"]

        changed = await db.update(
            "checkins", {"note": "edited"}, where="id = :id", params={"id": created["id"]}
        )
        deleted = await db.execute("delete from public.checkins where id = :id", id=created["id"])
        gone = await db.select("checkins", where="id = :id", params={"id": created["id"]})

        assert (changed, deleted) == (1, 1)
        assert gone == []


async def test_only_the_system_can_write_a_risk_verdict(
    people: dict[str, UUID], make_token: Any, analysis_of_a: Row
) -> None:
    """`analyses` is read-only through user_client: nobody edits their own diagnosis.

    Each attempt gets its own client, because a rejected statement aborts its transaction in
    Postgres — the request would end there in production too.
    """
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="permission denied for table analyses"):
            await db.insert(
                "analyses",
                {"patient_id": people["patient_a"], "risk": "low", "summary": "all fine"},
            )

    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="permission denied for table analyses"):
            await db.update(
                "analyses",
                {"risk": "low"},
                where="id = :id",
                params={"id": analysis_of_a["id"]},
            )


async def test_a_patient_cannot_promote_themselves_to_clinician(
    people: dict[str, UUID], make_token: Any
) -> None:
    """The role column is guarded by a policy, so a self-service edit cannot change a role."""
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.update(
                "profiles",
                {"role": "clinician"},
                where="id = :id",
                params={"id": people["patient_a"]},
            )

    async with user_client(make_token(people["patient_a"])) as db:
        changed = await db.update(
            "profiles",
            {"display_name": "Renamed by self"},
            where="id = :id",
            params={"id": people["patient_a"]},
        )
        assert changed == 1

    async with service_client() as audit:
        row = await audit.select(
            "profiles",
            columns=("role", "display_name"),
            where="id = :id",
            params={"id": people["patient_a"]},
        )
    assert (row[0]["role"], row[0]["display_name"]) == ("patient", "Renamed by self")


async def test_a_token_claim_of_being_a_clinician_counts_for_nothing(
    people: dict[str, UUID], make_token: Any, consent: Any, checkin_of_b: Row
) -> None:
    """Authorisation reads `profiles.role`; a `role` claim inside the token is decoration."""
    await consent(people["patient_b"])  # B is linked to the real clinician, not to A

    async with user_client(make_token(people["patient_a"], role="clinician")) as db:
        assert await db.select("checkins") == []
        assert (
            await db.select("profiles", where="id = :other", params={"other": people["patient_b"]})
            == []
        )


async def test_a_subject_with_no_profile_sees_nothing(
    people: dict[str, UUID],
    make_token: Any,
    checkin_of_a: Row,
    analysis_of_a: Row,
    alert_for_a: Row,
) -> None:
    """A valid signature is not an account: with no profiles row, every read comes back empty."""
    async with user_client(make_token(people["stranger"])) as db:
        for table in ("profiles", "checkins", "analyses", "alerts", "consents"):
            assert await db.select(table) == [], f"{table} leaked to an unknown subject"


async def test_a_patient_cannot_read_another_patients_consents(
    people: dict[str, UUID], make_token: Any, consent: Any
) -> None:
    """Consent rows are visible to the two parties named in them, and to no one else."""
    row = await consent(people["patient_a"], people["other_clinician"])

    async with user_client(make_token(people["patient_b"])) as db:
        assert await db.select("consents") == []

    async with user_client(make_token(people["patient_a"])) as db:
        mine = await db.select("consents")
    assert [item["id"] for item in mine] == [row["id"]]


async def test_a_patient_cannot_move_their_row_into_someone_elses_history(
    people: dict[str, UUID], make_token: Any, checkin_of_a: Row
) -> None:
    """Re-homing a row the caller can already see is refused by `with check`, not by `using`."""
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.update(
                "checkins",
                {"patient_id": people["patient_b"]},
                where="id = :id",
                params={"id": checkin_of_a["id"]},
            )

    async with service_client() as audit:
        stored = await audit.select(
            "checkins",
            columns=("patient_id",),
            where="id = :id",
            params={"id": checkin_of_a["id"]},
        )
    assert stored[0]["patient_id"] == people["patient_a"]
