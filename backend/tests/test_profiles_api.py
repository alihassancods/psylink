"""``POST /api/profiles/me`` and ``/me/update``: the onboarding door.

Runs against the real database as the real ``authenticated`` role, so these assertions
are the RLS policies speaking. The properties that matter:

* a signed-in account with no profile can create exactly its own, and only as a patient;
* a second create is a 409, not a silent second row;
* after bootstrapping, ``/auth/me`` works — that was the whole point;
* renaming touches the caller's own row and refuses without one;
* nothing here answers without a valid token.
"""

from uuid import UUID, uuid4

import pytest

from app.models.profile import UserRole
from app.services.db import service_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def clean_auth_user() -> UUID:
    """An auth-user id with no profile yet, removed again after the test."""
    user_id = uuid4()
    yield user_id
    async with service_client() as db:
        await db.execute(
            "delete from public.profiles where id = cast(:id as uuid)", id=str(user_id)
        )


async def test_bootstrap_creates_own_patient_profile(api_client, make_token, clean_auth_user):
    response = await api_client.post(
        "/api/profiles/me",
        headers=bearer(make_token(clean_auth_user)),
        json={"display_name": "  New Patient  "},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"id": str(clean_auth_user), "role": "patient", "display_name": "New Patient"}

    me = await api_client.get("/auth/me", headers=bearer(make_token(clean_auth_user)))
    assert me.status_code == 200
    assert me.json()["role"] == "patient"


async def test_bootstrap_twice_is_a_conflict(api_client, make_token, clean_auth_user):
    first = await api_client.post(
        "/api/profiles/me", headers=bearer(make_token(clean_auth_user)), json={"display_name": "Pat"}
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/profiles/me", headers=bearer(make_token(clean_auth_user)), json={"display_name": "Pat"}
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "profile_exists"


async def test_bootstrap_needs_a_valid_token(api_client, clean_auth_user):
    anonymous = await api_client.post("/api/profiles/me", json={"display_name": "Sneaky"})
    assert anonymous.status_code == 401

    garbage = await api_client.post(
        "/api/profiles/me", headers=bearer("not-a-jwt"), json={"display_name": "Sneaky"}
    )
    assert garbage.status_code == 401


async def test_bootstrap_ignores_any_role_the_body_claims(
    api_client, make_token, clean_auth_user, rows_for
):
    response = await api_client.post(
        "/api/profiles/me",
        headers=bearer(make_token(clean_auth_user)),
        json={"display_name": "Dr Self-Appointed", "role": "clinician"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "patient"
    stored = await rows_for("profiles", where="id = cast(:id as uuid)", id=str(clean_auth_user))
    assert stored[0]["role"] == "patient"


async def test_rename_updates_own_profile(api_client, make_token, seed_profile, rows_for):
    user_id = await seed_profile(role=UserRole.PATIENT, display_name="Old Name")

    response = await api_client.post(
        "/api/profiles/me/update",
        headers=bearer(make_token(user_id)),
        json={"display_name": "Chosen Name"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Chosen Name"

    stored = await rows_for("profiles", where="id = cast(:id as uuid)", id=str(user_id))
    assert stored[0]["display_name"] == "Chosen Name"
    assert str(stored[0]["role"]) == "patient"


async def test_rename_without_a_profile_is_404(api_client, make_token, clean_auth_user):
    response = await api_client.post(
        "/api/profiles/me/update",
        headers=bearer(make_token(clean_auth_user)),
        json={"display_name": "Nothing Here"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"


async def test_blank_name_is_refused(api_client, make_token, seed_profile):
    user_id = await seed_profile(display_name="Not Blank")

    response = await api_client.post(
        "/api/profiles/me/update", headers=bearer(make_token(user_id)), json={"display_name": "   "}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "display_name_required"
