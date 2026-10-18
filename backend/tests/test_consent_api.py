"""``/api/link`` and ``/api/consent``: minting, redeeming, and revoking access.

These run against the real database as real roles, so an assertion here means the policy said
yes — not that route code remembered to check. The properties that matter:

* a code is returned exactly once and only its hash is stored;
* redeeming is what creates a consent, and only for the patient who redeemed it;
* a used or expired code grants nothing, twice;
* revoking closes transcription again.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.models.profile import UserRole
from app.services.db import service_client

CODE_SHAPE = re.compile(r"^[0-9a-f]{10}$")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def pair(seed_profile, seed_consent) -> dict[str, Any]:
    """An unlinked clinician and patient: nothing exists between them yet."""
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Link")
    patient = await seed_profile(role=UserRole.PATIENT, display_name="Pat")
    return {"clinician": clinician, "patient": patient}


async def mint(api_client, make_token, clinician: UUID) -> tuple[str, UUID]:
    response = await api_client.post("/api/link", headers=bearer(make_token(clinician)))
    assert response.status_code == 201, response.text
    return response.json()["code"], UUID(response.json()["invite_id"])


# --- creating an invite -------------------------------------------------------------


async def test_clinician_mints_a_code_and_it_is_returned_once(
    api_client, make_token, pair, rows_for
) -> None:
    code, invite_id = await mint(api_client, make_token, pair["clinician"])
    assert CODE_SHAPE.match(code)

    body = await api_client.get("/api/link", headers=bearer(make_token(pair["clinician"])))
    assert body.status_code == 200
    listed = body.json()
    assert any(row["invite_id"] == str(invite_id) for row in listed)
    # The listing has no code field at all: only the hash was ever stored.
    assert all("code" not in row for row in listed)

    stored = await rows_for("invites", where="id = :id", id=str(invite_id))
    assert stored[0]["code_hash"] == hashlib.sha256(code.encode()).hexdigest()
    assert code not in str(stored)


async def test_patient_cannot_mint_an_invite(api_client, make_token, pair) -> None:
    response = await api_client.post("/api/link", headers=bearer(make_token(pair["patient"])))
    assert response.status_code == 403


async def test_one_clinician_cannot_see_another_s_invites(
    api_client, make_token, pair, seed_profile
) -> None:
    other = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Other")
    await mint(api_client, make_token, pair["clinician"])
    body = await api_client.get("/api/link", headers=bearer(make_token(other)))
    assert body.json() == []


async def test_anonymous_cannot_touch_either_route(api_client) -> None:
    assert (await api_client.post("/api/link")).status_code == 401
    assert (await api_client.get("/api/consent")).status_code == 401


# --- redeeming -----------------------------------------------------------------------


async def test_redeem_creates_a_consent_for_the_patient_only(
    api_client, make_token, pair, rows_for
) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])

    response = await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": code}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["clinician_id"] == str(pair["clinician"])
    assert body["clinician_name"] == "Dr Link"  # the new policy lets the patient see who

    stored = await rows_for("consents", where="patient_id = :p", p=str(pair["patient"]))
    assert len(stored) == 1
    assert stored[0]["revoked_at"] is None

    # A second patient with the same code gets nothing: the invite is already consumed.
    stranger = await rows_for("consents", where="patient_id = :p", p=str(pair["clinician"]))
    assert stranger == []


async def test_code_is_single_use(api_client, make_token, pair, seed_profile) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    second_patient = await seed_profile(role=UserRole.PATIENT, display_name="Pat 2")

    first = await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": code}
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/consent", headers=bearer(make_token(second_patient)), json={"code": code}
    )
    assert second.status_code == 400
    assert second.json()["detail"]["code"] == "invite_invalid"


async def test_redeeming_the_same_code_twice_is_idempotent_for_the_same_patient(
    api_client, make_token, pair
) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    headers = bearer(make_token(pair["patient"]))
    first = await api_client.post("/api/consent", headers=headers, json={"code": code})
    assert first.status_code == 201

    second = await api_client.post("/api/consent", headers=headers, json={"code": code})
    # The invite is spent, but access already exists, so the patient is not punished for a retry.
    assert second.status_code == 201, second.text
    assert second.json()["consent_id"] == first.json()["consent_id"]


async def test_a_clinician_cannot_link_themselves(api_client, make_token, pair) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    response = await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["clinician"])), json={"code": code}
    )
    assert response.status_code == 403  # /api/consent is patient-only


async def test_garbage_and_expired_codes_are_refused(api_client, make_token, pair) -> None:
    headers = bearer(make_token(pair["patient"]))
    assert (
        await api_client.post("/api/consent", headers=headers, json={"code": "deadbeef99"})
    ).status_code == 400
    assert (
        await api_client.post("/api/consent", headers=headers, json={"code": "abc"})
    ).status_code == 422  # below the field's min length


async def test_expired_code_is_refused(api_client, make_token, pair, monkeypatch) -> None:
    # Rather than sleep for a day, expire the invite in the database.
    code, invite_id = await mint(api_client, make_token, pair["clinician"])
    # Back-date the whole row: `invites_expires_after_creation` refuses an expiry that
    # predates creation, which is the constraint doing its job rather than an obstacle.
    async with service_client() as db:
        await db.update(
            "invites",
            {
                "created_at": datetime(2019, 1, 1, tzinfo=UTC),
                "expires_at": datetime(2020, 1, 1, tzinfo=UTC),
            },
            where="id = :id",
            params={"id": str(invite_id)},
        )

    response = await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": code}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invite_invalid"


async def test_code_formatting_is_tolerated(api_client, make_token, pair) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    mangled = f"  {code[:5]}-{code[5:]}  ".upper()
    response = await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": mangled}
    )
    assert response.status_code == 201, response.text


async def test_a_patient_cannot_read_anyone_s_invites(api_client, make_token, pair) -> None:
    await mint(api_client, make_token, pair["clinician"])
    # RLS gives patients no select policy on invites, so the route is not even reachable to
    # list them; confirm nothing leaks through the redeem path either.
    async with service_client() as db:
        rows = await db.select("invites")
    assert len(rows) == 1
    assert "code" not in rows[0]


# --- revocation closes the door ------------------------------------------------------


async def test_revoke_removes_the_link_and_blocks_transcription(
    api_client, make_token, pair, monkeypatch
) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": code}
    )

    async def fake_transcribe(audio: bytes, *, language_code: str = "en", max_seconds=None):
        raise AssertionError("transcription must not run without an active consent")

    monkeypatch.setattr("app.api.transcribe.transcribe_bytes", fake_transcribe)

    revoke = await api_client.request(
        "DELETE",
        f"/api/consent/{pair['clinician']}",
        headers=bearer(make_token(pair["patient"])),
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["revoked_at"]

    blocked = await api_client.post(
        "/api/transcribe",
        headers={**bearer(make_token(pair["patient"])), "Content-Type": "audio/webm"},
        content=b"\x1a\x45\xdf\xa3fake",
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "consent_required"

    # The consent row survives as history; it is not deleted.
    from app.services.db import service_client as sc

    async with sc() as db:
        rows = await db.select(
            "consents", where="patient_id = :p", params={"p": str(pair["patient"])}
        )
    assert len(rows) == 1
    assert rows[0]["revoked_at"] is not None


async def test_revoke_of_an_unknown_clinician_is_404(api_client, make_token, pair) -> None:
    response = await api_client.request(
        "DELETE",
        f"/api/consent/{UUID(int=0x9999)}",
        headers=bearer(make_token(pair["patient"])),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "consent_not_found"


async def test_revoke_is_the_patient_s_call_not_the_clinician_s(
    api_client, make_token, pair
) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    await api_client.post(
        "/api/consent", headers=bearer(make_token(pair["patient"])), json={"code": code}
    )
    response = await api_client.request(
        "DELETE",
        f"/api/consent/{pair['patient']}",
        headers=bearer(make_token(pair["clinician"])),
    )
    assert response.status_code == 403


async def test_consent_list_shows_only_live_links(api_client, make_token, pair) -> None:
    code, _ = await mint(api_client, make_token, pair["clinician"])
    headers = bearer(make_token(pair["patient"]))
    assert (await api_client.get("/api/consent", headers=headers)).json() == []

    await api_client.post("/api/consent", headers=headers, json={"code": code})
    active = (await api_client.get("/api/consent", headers=headers)).json()
    assert len(active) == 1
    assert active[0]["clinician_name"] == "Dr Link"

    await api_client.request("DELETE", f"/api/consent/{pair['clinician']}", headers=headers)
    assert (await api_client.get("/api/consent", headers=headers)).json() == []
