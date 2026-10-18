"""Clinician access is a function of one thing only: an active consent.

The three cases the design rests on — an unlinked patient is invisible, revoking access takes the
history away too, and re-granting gives it back — are asserted against check-ins, analyses, and
alerts separately, because each table carries its own policy.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from app.services.db import Row, service_client, user_client


async def test_an_unlinked_clinician_sees_nothing(
    people: dict[str, UUID],
    make_token: Any,
    checkin_of_a: Row,
    analysis_of_a: Row,
    alert_for_a: Row,
) -> None:
    """No consent row — and the alert is even addressed to this clinician, still not visible."""
    async with user_client(make_token(people["clinician"])) as db:
        assert await db.select("checkins") == []
        assert await db.select("analyses") == []
        assert await db.select("alerts") == []
        assert await db.select("profiles", where="id = :p", params={"p": people["patient_a"]}) == []
        assert await db.select("consents") == []


async def test_a_different_clinician_is_not_the_linked_one(
    people: dict[str, UUID],
    make_token: Any,
    consent: Any,
    checkin_of_a: Row,
    alert_for_a: Row,
) -> None:
    await consent()  # links patient_a to `clinician`

    async with user_client(make_token(people["other_clinician"])) as db:
        assert await db.select("checkins") == []
        assert await db.select("alerts") == []


async def test_linking_a_patient_opens_their_rows(
    people: dict[str, UUID],
    make_token: Any,
    consent: Any,
    checkin_of_a: Row,
    analysis_of_a: Row,
    alert_for_a: Row,
) -> None:
    await consent()

    async with user_client(make_token(people["clinician"])) as db:
        checkins = await db.select("checkins")
        analyses = await db.select("analyses")
        alerts = await db.select("alerts")
        roster = await db.select("profiles", order_by="display_name")
        links = await db.select("consents")

    assert [row["id"] for row in checkins] == [checkin_of_a["id"]]
    assert [row["id"] for row in analyses] == [analysis_of_a["id"]]
    assert [row["id"] for row in alerts] == [alert_for_a["id"]]
    assert {row["id"] for row in roster} == {people["patient_a"], people["clinician"]}
    assert len(links) == 1


async def test_revoking_access_hides_past_rows_too(
    people: dict[str, UUID],
    make_token: Any,
    consent: Any,
    checkin_of_a: Row,
    analysis_of_a: Row,
    alert_for_a: Row,
) -> None:
    row = await consent()

    async with user_client(make_token(people["clinician"])) as db:
        assert len(await db.select("checkins")) == 1

    # The patient revokes through their own client: consent is theirs to withdraw.
    async with user_client(make_token(people["patient_a"])) as db:
        changed = await db.update(
            "consents",
            {"revoked_at": datetime.now(UTC)},
            where="id = :id",
            params={"id": row["id"]},
        )
    assert changed == 1

    async with user_client(make_token(people["clinician"])) as db:
        assert await db.select("checkins") == []
        assert await db.select("analyses") == []
        assert await db.select("alerts") == [], "revocation covers the historic work queue"
        assert await db.select("profiles", where="id = :p", params={"p": people["patient_a"]}) == []
        assert await db.scalar("select app.has_active_consent(:p)", p=people["patient_a"]) is False

        # An update against a row that is no longer visible changes nothing.
        assert (
            await db.update(
                "alerts",
                {"acknowledged_at": datetime.now(UTC), "acknowledged_by": people["clinician"]},
                where="id = :id",
                params={"id": alert_for_a["id"]},
            )
            == 0
        )


async def test_re_granting_by_inserting_restores_access(
    people: dict[str, UUID],
    make_token: Any,
    consent: Any,
    checkin_of_a: Row,
    alert_for_a: Row,
) -> None:
    first = await consent()

    async with user_client(make_token(people["patient_a"])) as db:
        await db.update(
            "consents",
            {"revoked_at": datetime.now(UTC)},
            where="id = :id",
            params={"id": first["id"]},
        )

    async with user_client(make_token(people["clinician"])) as db:
        assert await db.select("checkins") == []

    async with user_client(make_token(people["patient_a"])) as db:
        again = await db.insert(
            "consents", {"patient_id": people["patient_a"], "clinician_id": people["clinician"]}
        )

    assert again is not None and again["revoked_at"] is None

    async with user_client(make_token(people["clinician"])) as db:
        assert [row["id"] for row in await db.select("checkins")] == [checkin_of_a["id"]]
        assert [row["id"] for row in await db.select("alerts")] == [alert_for_a["id"]]
        assert await db.scalar("select app.has_active_consent(:p)", p=people["patient_a"]) is True


async def test_re_granting_by_clearing_the_revocation_works_as_well(
    people: dict[str, UUID],
    make_token: Any,
    consent: Any,
    checkin_of_a: Row,
) -> None:
    row = await consent()

    async with user_client(make_token(people["patient_a"])) as db:
        await db.update(
            "consents",
            {"revoked_at": datetime.now(UTC)},
            where="id = :id",
            params={"id": row["id"]},
        )

    async with user_client(make_token(people["clinician"])) as db:
        assert await db.select("checkins") == []

    async with user_client(make_token(people["patient_a"])) as db:
        changed = await db.update(
            "consents", {"revoked_at": None}, where="id = :id", params={"id": row["id"]}
        )
    assert changed == 1

    async with user_client(make_token(people["clinician"])) as db:
        assert len(await db.select("checkins")) == 1


async def test_a_clinician_cannot_write_patient_data(
    people: dict[str, UUID], make_token: Any, consent: Any, checkin_of_a: Row
) -> None:
    """Reading is the whole grant: check-ins belong to the patient, analyses to the pipeline.

    One client per attempt: a rejected statement aborts its transaction in Postgres, exactly as
    it would end the request that made it.
    """
    await consent()
    clinician = make_token(people["clinician"])

    async with user_client(clinician) as db:
        # checkins: the role may write the table, but no policy matches a clinician as patient_id.
        assert (
            await db.update(
                "checkins",
                {"note": "edited by clinician"},
                where="id = :id",
                params={"id": checkin_of_a["id"]},
            )
            == 0
        )

    async with user_client(clinician) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.insert("checkins", {"patient_id": people["patient_a"], "answers": {}})

    async with user_client(clinician) as db:
        # analyses: no write privilege at all, so the attempt is refused before RLS is consulted.
        with pytest.raises(DBAPIError, match="permission denied for table analyses"):
            await db.update(
                "analyses",
                {"summary": "rewritten"},
                where="id = :id",
                params={"id": checkin_of_a["id"]},
            )

    async with user_client(make_token(people["patient_a"])) as db:
        stored = await db.select(
            "checkins", columns=("note",), where="id = :id", params={"id": checkin_of_a["id"]}
        )
    assert stored[0]["note"] == "felt awful this morning"


async def test_a_clinician_acknowledges_their_own_open_alert(
    people: dict[str, UUID], make_token: Any, consent: Any, alert_for_a: Row
) -> None:
    await consent()

    async with user_client(make_token(people["clinician"])) as db:
        changed = await db.update(
            "alerts",
            {"acknowledged_at": datetime.now(UTC), "acknowledged_by": people["clinician"]},
            where="id = :id",
            params={"id": alert_for_a["id"]},
        )
        assert changed == 1

        seen = await db.select(
            "alerts",
            columns=("acknowledged_at", "acknowledged_by"),
            where="id = :id",
            params={"id": alert_for_a["id"]},
        )

    assert seen[0]["acknowledged_at"] is not None
    assert seen[0]["acknowledged_by"] == people["clinician"]

    # An alert addressed to someone else is not this clinician's to acknowledge.
    async with user_client(make_token(people["other_clinician"])) as db:
        assert (
            await db.update(
                "alerts",
                {
                    "acknowledged_at": datetime.now(UTC),
                    "acknowledged_by": people["other_clinician"],
                },
                where="id = :id",
                params={"id": alert_for_a["id"]},
            )
            == 0
        )


async def test_a_clinician_cannot_repoint_an_alert_to_a_patient_they_cannot_see(
    people: dict[str, UUID], make_token: Any, consent: Any, alert_for_a: Row
) -> None:
    """`with check` re-runs the consent test on the new values, not just the old ones."""
    await consent()

    async with user_client(make_token(people["clinician"])) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            await db.update(
                "alerts",
                {"patient_id": people["patient_b"]},
                where="id = :id",
                params={"id": alert_for_a["id"]},
            )

    async with service_client() as audit:
        stored = await audit.select(
            "alerts",
            columns=("patient_id",),
            where="id = :id",
            params={"id": alert_for_a["id"]},
        )
    assert stored[0]["patient_id"] == people["patient_a"]


async def test_a_patient_can_grant_but_not_erase_the_grant_history(
    people: dict[str, UUID], make_token: Any, checkin_of_a: Row
) -> None:
    """Consent is withdrawn by stamping `revoked_at`; the rows themselves are not deletable."""
    async with user_client(make_token(people["patient_a"])) as db:
        granted = await db.insert(
            "consents", {"patient_id": people["patient_a"], "clinician_id": people["clinician"]}
        )
        assert granted is not None

        with pytest.raises(DBAPIError, match="permission denied for table consents"):
            await db.execute("delete from public.consents where id = :id", id=granted["id"])


async def test_a_patient_cannot_grant_access_to_a_nonexistent_clinician(
    people: dict[str, UUID], make_token: Any
) -> None:
    """RLS lets a patient write their own consent rows; the foreign key keeps them real."""
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="violates foreign key constraint"):
            await db.insert(
                "consents", {"patient_id": people["patient_a"], "clinician_id": uuid4()}
            )


async def test_a_consent_cannot_be_linked_to_itself(
    people: dict[str, UUID], make_token: Any
) -> None:
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(DBAPIError, match="consents_not_self_referential"):
            await db.insert(
                "consents",
                {"patient_id": people["patient_a"], "clinician_id": people["patient_a"]},
            )
