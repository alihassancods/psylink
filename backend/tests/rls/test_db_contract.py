"""The three names other components build on: user_client, service_client, has_active_consent.

These assert the *shape* of the contract — what each client can see, which tokens are refused,
and that an identity never outlives the transaction that assumed it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.security import AuthError
from app.services.db import Json, Row, has_active_consent, service_client, user_client


async def test_service_client_sees_what_a_patient_cannot(
    people: dict[str, UUID],
    make_token: Any,
    checkin_of_a: Row,
    checkin_of_b: Row,
) -> None:
    async with service_client() as db:
        everything = await db.select("checkins")
        assert len(everything) == 2
        assert await db.scalar("select current_user <> 'authenticated'") is True

    async with user_client(make_token(people["patient_a"])) as db:
        mine = await db.select("checkins")
        assert len(mine) == 1
        assert await db.scalar("select current_user") == "authenticated"
        assert await db.scalar("select app.current_user_id()") == people["patient_a"]


async def test_an_identity_does_not_outlive_its_transaction(
    people: dict[str, UUID], make_token: Any, checkin_of_a: Row
) -> None:
    """`SET LOCAL` is the whole defence against a pooled connection carrying a caller over."""
    async with user_client(make_token(people["patient_a"])) as db:
        await db.fetch("select 1")

    # The same pooled connection, now without a request: no role, no claims.
    async with service_client() as db:
        assert await db.scalar("select current_user <> 'authenticated'") is True
        assert await db.scalar("select app.current_user_id()") is None

    async with user_client(make_token(people["patient_b"])) as db:
        assert await db.select("checkins") == [], "B must not inherit A's visibility"


async def test_a_token_that_does_not_verify_never_reaches_the_database(
    people: dict[str, UUID], make_token: Any, checkin_of_a: Row
) -> None:
    patient_a = people["patient_a"]

    with pytest.raises(AuthError, match="not valid"):
        async with user_client(make_token(patient_a, secret="an-other-hs256-secret-0123456789ab")):
            pass

    with pytest.raises(AuthError, match="expired"):
        async with user_client(make_token(patient_a, lifetime=timedelta(hours=-2))):
            pass

    with pytest.raises(AuthError, match="not valid"):
        async with user_client(make_token(patient_a, audience="anon")):
            pass

    # A well-signed token whose subject is not an id is still a refusal, not a fallback.
    with pytest.raises(AuthError, match="not a user id"):
        async with user_client(make_token("patient-a")):
            pass


@pytest.mark.parametrize(
    "table",
    ["profiles", "consents", "checkins", "analyses", "alerts"],
)
async def test_anonymous_has_no_route_in(
    table: str, people: dict[str, UUID], checkin_of_a: Row
) -> None:
    """`anon` holds no privilege on any of these tables, so RLS is not the only gate."""
    async with service_client() as db:
        permitted = await db.scalar(
            f"select has_table_privilege('anon', 'public.{table}'::regclass, 'SELECT')"
        )
    assert permitted is False


async def test_consent_is_checked_from_the_holders_own_client(
    people: dict[str, UUID], make_token: Any, consent: Any, checkin_of_a: Row
) -> None:
    await consent()

    async with user_client(make_token(people["clinician"])) as db:
        assert await has_active_consent(people["patient_a"], client=db) is True
        assert await has_active_consent(people["patient_b"], client=db) is False

    async with user_client(make_token(people["patient_a"])) as db:
        assert await has_active_consent(people["patient_a"], client=db) is False, (
            "A is not this patient's clinician, whatever else A may see"
        )


async def test_consent_can_be_asked_with_a_bearer_token(
    people: dict[str, UUID], make_token: Any, consent: Any, checkin_of_a: Row
) -> None:
    await consent()

    assert (
        await has_active_consent(people["patient_a"], token=make_token(people["clinician"])) is True
    )
    assert (
        await has_active_consent(people["patient_a"], token=make_token(people["other_clinician"]))
        is False
    )


async def test_consent_can_be_asked_as_a_service_job(
    people: dict[str, UUID], consent: Any, checkin_of_a: Row
) -> None:
    """Pipeline code has no request in hand, so it names the pair explicitly."""
    await consent()

    assert await has_active_consent(people["patient_a"], clinician_id=people["clinician"]) is True
    unlinked = await has_active_consent(people["patient_a"], clinician_id=people["other_clinician"])
    assert unlinked is False


async def test_consent_refuses_to_guess_which_clinician_is_meant(
    people: dict[str, UUID],
) -> None:
    """No client, no token, no explicit pair: there is no safe default, so this is a bug to fix."""
    with pytest.raises(ValueError, match="needs one of client"):
        await has_active_consent(people["patient_a"])


async def test_a_revoked_consent_fails_the_helper_too(
    people: dict[str, UUID], make_token: Any, consent: Any, checkin_of_a: Row
) -> None:
    row = await consent()

    async with user_client(make_token(people["patient_a"])) as db:
        await db.update(
            "consents",
            {"revoked_at": datetime.now(UTC)},
            where="id = :id",
            params={"id": row["id"]},
        )

    assert await has_active_consent(people["patient_a"], clinician_id=people["clinician"]) is False


async def test_names_of_tables_and_columns_are_checked_not_interpolated(
    people: dict[str, UUID], make_token: Any
) -> None:
    """`where` is SQL by contract, but the identifiers around it are never free-form."""
    async with user_client(make_token(people["patient_a"])) as db:
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            await db.select("checkins; drop table public.profiles")

        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            await db.select("checkins", columns=("note from profiles --",))

        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            await db.insert("checkins", {"patient_id; --": people["patient_a"]})

    async with service_client() as db:
        assert await db.scalar("select count(*) from public.profiles") is not None


async def test_json_wraps_a_document_that_is_not_an_object(
    people: dict[str, UUID], insert_row: Any
) -> None:
    row = await insert_row(
        "analyses",
        {
            "patient_id": people["patient_a"],
            "summary": "flags as a list",
            "signals": Json([{"code": "pain_slope", "value": 1.4}]),
        },
    )

    async with service_client() as db:
        stored = await db.select(
            "analyses", columns=("signals",), where="id = :id", params={"id": row["id"]}
        )
    assert stored[0]["signals"] == [{"code": "pain_slope", "value": 1.4}]


async def test_writes_through_user_client_are_committed_with_the_transaction(
    people: dict[str, UUID], make_token: Any
) -> None:
    """The client commits on exit, so the next request — from any connection — sees the row."""
    async with user_client(make_token(people["patient_a"])) as db:
        created = await db.insert(
            "checkins", {"patient_id": people["patient_a"], "answers": {"mood": 2}}
        )

    async with user_client(make_token(people["patient_a"])) as db:
        again = await db.select("checkins", where="id = :id", params={"id": created["id"]})
    assert len(again) == 1

    with pytest.raises(DBAPIError, match="checkins_answers_are_objects"):
        async with service_client() as db:
            await db.insert("checkins", {"patient_id": people["patient_a"], "answers": Json([1])})
