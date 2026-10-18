"""The migrations left the database in the shape the design promises.

These are the invariants the access rules depend on — RLS switched on, no permissive policy
anywhere, the two indexes that make the hot queries sane, and the helpers the policies call.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError

from app.services.db import service_client

TABLES = ["profiles", "consents", "checkins", "analyses", "alerts"]


async def test_row_level_security_is_on_for_every_table() -> None:
    async with service_client() as db:
        rows = await db.fetch(
            "select relname as name, relrowsecurity as on_, relforcerowsecurity as forced "
            "from pg_class where relnamespace = 'public'::regnamespace "
            "and relname = any(cast(:names as text[]))",
            names=TABLES,
        )

    assert len(rows) == len(TABLES), "every table was found"
    assert all(row["on_"] is True for row in rows), [row["name"] for row in rows if not row["on_"]]

    forced = [row["name"] for row in rows if row["forced"]]
    # The service client depends on the owner being exempt: forcing RLS would block system writes.
    assert not forced, f"forced row security on {forced} would stop service_client"


async def test_the_two_hot_indexes_exist_as_specified() -> None:
    async with service_client() as db:
        rows = await db.fetch(
            "select indexname as name, indexdef as definition from pg_indexes "
            "where schemaname = 'public' "
            "and indexname = any(cast(:names as text[]))",
            names=["checkins_patient_created_idx", "alerts_clinician_ack_idx"],
        )

    definitions = {row["name"]: row["definition"].lower() for row in rows}
    assert set(definitions) == {
        "checkins_patient_created_idx",
        "alerts_clinician_ack_idx",
    }
    assert "(patient_id, created_at desc)" in definitions["checkins_patient_created_idx"]
    assert "(clinician_id, acknowledged_at)" in definitions["alerts_clinician_ack_idx"]


async def test_the_policy_helpers_are_installed() -> None:
    expected = [
        "jwt_claim",
        "current_user_id",
        "current_user_role",
        "is_patient",
        "is_clinician",
        "has_active_consent",
    ]

    async with service_client() as db:
        found = await db.fetch(
            "select p.proname as name from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'app' and p.proname = any(cast(:names as text[]))",
            names=expected,
        )

    assert sorted(row["name"] for row in found) == sorted(expected)


async def test_no_policy_is_permissive() -> None:
    """A policy with no expression is `using (true)`, which is what this whole file prevents."""
    async with service_client() as db:
        rows = await db.fetch(
            "select policyname as name, tablename as table_name, qual, with_check "
            "from pg_policies where schemaname = 'public'"
        )

    assert len(rows) >= 10, "the policies were created"
    for row in rows:
        assert row["qual"] or row["with_check"], f"{row['name']} has no condition"
        for expression in (row["qual"], row["with_check"]):
            if expression is not None:
                assert expression.strip() != "true", f"{row['name']} is wide open"


async def test_policies_apply_to_authenticated_requests_only() -> None:
    """Every policy names `authenticated` explicitly, leaving `anon` and the owner out of it."""
    async with service_client() as db:
        rows = await db.fetch(
            "select policyname as name, array_to_string(roles, ',') as roles "
            "from pg_policies where schemaname = 'public'"
        )

    assert rows, "policies exist"
    for row in rows:
        assert row["roles"] == "authenticated", f"{row['name']} applies to {row['roles']}"


async def test_helpers_fail_closed_without_a_request() -> None:
    """On the service connection nobody is the caller, so identity lookups come back empty."""
    async with service_client() as db:
        assert await db.scalar("select app.current_user_id()") is None
        assert await db.scalar("select app.current_user_role()") is None
        assert await db.scalar("select app.is_clinician()") is None
        assert await db.scalar("select app.has_active_consent(gen_random_uuid())") is False


async def test_only_one_active_consent_per_pair(
    people: dict[str, Any], insert_row: Any, consent: Any
) -> None:
    await consent()

    with pytest.raises(DBAPIError, match="consents_active_pair_key"):
        await insert_row(
            "consents",
            {"patient_id": people["patient_a"], "clinician_id": people["clinician"]},
        )

    # A second revoked row is history, not a live link, so the partial index lets it through.
    second = await consent(revoked_at=datetime.now(UTC))
    assert second["revoked_at"] is not None


async def test_risk_level_enum_holds_the_three_verdicts() -> None:
    async with service_client() as db:
        labels = await db.scalar("select array_to_string(enum_range(null::public.risk_level), ',')")
    assert labels == "low,medium,high"
