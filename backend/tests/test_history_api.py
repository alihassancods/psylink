"""1.11 patient history: what a patient may list, and what deleting one of their own means.

Everything here runs through the patient's real identity, so a passing assertion means row-level
security agreed — not that the route remembered to filter.
"""

from typing import Any
from uuid import UUID

import pytest

from app.models.profile import UserRole
from app.services.db import service_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def patients(seed_profile, seed_consent) -> dict[str, Any]:
    a = await seed_profile(role=UserRole.PATIENT, display_name="A")
    b = await seed_profile(role=UserRole.PATIENT, display_name="B")
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr")
    await seed_consent(a, clinician)
    await seed_consent(b, clinician)
    return {"a": a, "b": b, "clinician": clinician}


async def add_checkin(patient_id: UUID, *, transcript: str, risk: str | None = "low") -> str:
    """Insert a check-in and, optionally, the analysis a pipeline would have written."""
    async with service_client() as db:
        checkin = await db.insert(
            "checkins",
            {
                "patient_id": str(patient_id),
                "transcript": transcript,
                "analysis_status": "analyzed",
            },
        )
        if risk is not None:
            await db.insert(
                "analyses",
                {
                    "patient_id": str(patient_id),
                    "checkin_id": str(checkin["id"]),
                    "risk": risk,
                    "summary": f"Summary for {transcript[:16]}",
                },
            )
        return str(checkin["id"])


# --- listing ------------------------------------------------------------------------


async def test_patient_lists_only_their_own_checkins(api_client, make_token, patients) -> None:
    mine = await add_checkin(patients["a"], transcript="mine")
    theirs = await add_checkin(patients["b"], transcript="theirs")

    body = await api_client.get("/api/checkins", headers=bearer(make_token(patients["a"])))
    assert body.status_code == 200
    ids = [item["checkin_id"] for item in body.json()["items"]]
    assert mine in ids
    assert theirs not in ids


async def test_risk_is_reported_in_app_wording(api_client, make_token, patients) -> None:
    await add_checkin(patients["a"], transcript="rough", risk="medium")
    item = await api_client.get("/api/checkins", headers=bearer(make_token(patients["a"])))
    assert item.json()["items"][0]["risk"] == "moderate"  # the enum says 'medium'


async def test_unanalysed_checkins_appear_with_no_risk(api_client, make_token, patients) -> None:
    async with service_client() as db:
        row = await db.insert(
            "checkins",
            {
                "patient_id": str(patients["a"]),
                "transcript": "just saved",
                "analysis_status": "pending",
            },
        )
        checkin_id = str(row["id"])
    items = (
        await api_client.get("/api/checkins", headers=bearer(make_token(patients["a"])))
    ).json()["items"]
    found = next(i for i in items if i["checkin_id"] == checkin_id)
    assert found["status"] == "pending"
    assert found["risk"] is None
    assert found["summary"] is None


async def test_newest_first_and_paged(api_client, make_token, patients) -> None:
    ids = [await add_checkin(patients["a"], transcript=f"day {i}") for i in range(5)]
    page = (
        await api_client.get(
            "/api/checkins?limit=2&offset=0", headers=bearer(make_token(patients["a"]))
        )
    ).json()
    assert len(page["items"]) == 2
    # Created in the same transaction order, so the newest insert sorts first.
    assert page["items"][0]["checkin_id"] == ids[-1]
    page2 = (
        await api_client.get(
            "/api/checkins?limit=2&offset=2", headers=bearer(make_token(patients["a"]))
        )
    ).json()
    assert {i["checkin_id"] for i in page["items"]}.isdisjoint(
        {i["checkin_id"] for i in page2["items"]}
    )


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
async def test_pagination_bounds_are_validated(api_client, make_token, patients, query) -> None:
    response = await api_client.get(
        f"/api/checkins?{query}", headers=bearer(make_token(patients["a"]))
    )
    assert response.status_code == 422


async def test_clinician_cannot_use_the_patient_history_route(
    api_client, make_token, patients
) -> None:
    response = await api_client.get(
        "/api/checkins", headers=bearer(make_token(patients["clinician"]))
    )
    assert response.status_code == 403


async def test_anonymous_is_401(api_client) -> None:
    assert (await api_client.get("/api/checkins")).status_code == 401


# --- deleting -----------------------------------------------------------------------


async def test_delete_removes_the_checkin_and_its_analysis(
    api_client, make_token, patients, rows_for
) -> None:
    checkin_id = await add_checkin(patients["a"], transcript="take this back", risk="high")

    response = await api_client.delete(
        f"/api/checkins/{checkin_id}", headers=bearer(make_token(patients["a"]))
    )
    assert response.status_code == 204

    assert await rows_for("checkins", where="id = :id", id=checkin_id) == []
    # The summary derived from it goes too: it must not outlive the thing it described.
    assert await rows_for("analyses", where="checkin_id = :id", id=checkin_id) == []


async def test_delete_of_another_patient_s_checkin_is_404(api_client, make_token, patients) -> None:
    checkin_id = await add_checkin(patients["b"], transcript="not yours")
    response = await api_client.delete(
        f"/api/checkins/{checkin_id}", headers=bearer(make_token(patients["a"]))
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "checkin_not_found"

    # B's row is untouched.
    async with service_client() as db:
        assert await db.fetchrow("select id from public.checkins where id = :id", id=checkin_id)


async def test_delete_of_unknown_id_is_404(api_client, make_token, patients) -> None:
    response = await api_client.delete(
        f"/api/checkins/{UUID(int=0x1234)}", headers=bearer(make_token(patients["a"]))
    )
    assert response.status_code == 404


async def test_delete_twice_is_404_the_second_time(api_client, make_token, patients) -> None:
    checkin_id = await add_checkin(patients["a"], transcript="once")
    headers = bearer(make_token(patients["a"]))
    assert (
        await api_client.delete(f"/api/checkins/{checkin_id}", headers=headers)
    ).status_code == 204
    assert (
        await api_client.delete(f"/api/checkins/{checkin_id}", headers=headers)
    ).status_code == 404


async def test_deleting_a_checkin_leaves_the_alert_record(
    api_client, make_token, patients, rows_for
) -> None:
    """The clinician was paged: that happened, and deleting the source does not rewrite history."""
    checkin_id = await add_checkin(patients["a"], transcript="high risk", risk="high")
    async with service_client() as db:
        analysis = await db.fetchrow(
            "select id from public.analyses where checkin_id = :c", c=checkin_id
        )
        await db.insert(
            "alerts",
            {
                "patient_id": str(patients["a"]),
                "clinician_id": str(patients["clinician"]),
                "analysis_id": str(analysis["id"]),
                "severity": "high",
                "message": "High-risk check-in needs review",
            },
        )

    await api_client.delete(
        f"/api/checkins/{checkin_id}", headers=bearer(make_token(patients["a"]))
    )

    alerts = await rows_for("alerts", where="patient_id = :p", p=str(patients["a"]))
    assert len(alerts) == 1
    assert alerts[0]["analysis_id"] is None  # FK is `on delete set null`, and that is intended
