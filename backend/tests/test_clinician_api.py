"""1.12 clinician reads: roster, trend, and check-in detail — all gated by live consent.

The point of these tests is what a clinician *cannot* see. Each case is run through the real
database as the `authenticated` role, so an empty result here means a policy said so.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from app.models.profile import UserRole
from app.services.db import service_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def clinic(seed_profile, seed_consent) -> dict[str, Any]:
    """One clinician with one consented patient, one unconsented patient, and one colleague."""
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Seen")
    colleague = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Other")
    patient = await seed_profile(role=UserRole.PATIENT, display_name="Known Patient")
    stranger = await seed_profile(role=UserRole.PATIENT, display_name="Hidden Patient")
    await seed_consent(patient, clinician)
    await seed_consent(stranger, colleague)
    return {
        "clinician": clinician,
        "colleague": colleague,
        "patient": patient,
        "stranger": stranger,
    }


async def seed_checkin(
    patient_id: UUID,
    *,
    transcript: str,
    risk: str = "medium",
    mood: int = 3,
    when: datetime | None = None,
    evidence: str | None = None,
    model: str = "test/model",
) -> str:
    async with service_client() as db:
        columns = {
            "patient_id": str(patient_id),
            "transcript": transcript,
            "analysis_status": "analyzed",
        }
        if when is not None:
            columns["created_at"] = when
        checkin = await db.insert("checkins", columns)
        await db.insert(
            "analyses",
            {
                "patient_id": str(patient_id),
                "checkin_id": str(checkin["id"]),
                "risk": risk,
                "summary": "The patient reports poor sleep.",
                "model": model,
                "signals": {
                    "mood_score": mood,
                    "emotions": ["sad", "tired"],
                    "symptoms": {"sleep": 3, "appetite": None, "energy": 2},
                    "risk_source": "both" if evidence else "llm",
                    "risk_evidence": evidence,
                    "confidence": "medium",
                },
            },
        )
        return str(checkin["id"])


# --- roster -------------------------------------------------------------------------


async def test_roster_lists_only_consented_patients(api_client, make_token, clinic) -> None:
    await seed_checkin(clinic["patient"], transcript="slept badly")
    await seed_checkin(clinic["stranger"], transcript="not yours")

    body = await api_client.get("/api/patients", headers=bearer(make_token(clinic["clinician"])))
    assert body.status_code == 200
    data = body.json()
    ids = [item["patient_id"] for item in data["items"]]
    assert ids == [str(clinic["patient"])]
    assert data["total"] == 1
    assert data["items"][0]["last_risk"] == "moderate"  # enum 'medium' -> app 'moderate'
    assert data["items"][0]["last_checkin_at"]


async def test_revoking_consent_drops_the_patient_from_the_roster(
    api_client, make_token, clinic
) -> None:
    await seed_checkin(clinic["patient"], transcript="slept badly")
    headers = bearer(make_token(clinic["patient"]))
    await api_client.request("DELETE", f"/api/consent/{clinic['clinician']}", headers=headers)

    data = (
        await api_client.get("/api/patients", headers=bearer(make_token(clinic["clinician"])))
    ).json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_open_alerts_count_and_order_the_roster(
    api_client, make_token, clinic, seed_profile
) -> None:
    checkin_id = await seed_checkin(clinic["patient"], transcript="high", risk="high")
    async with service_client() as db:
        analysis = await db.fetchrow(
            "select id from public.analyses where checkin_id = :c", c=checkin_id
        )
        other_patient = await db.fetchrow(
            "select id from public.profiles where role = 'patient' limit 1"
        )
        await db.insert(
            "alerts",
            {
                "patient_id": str(clinic["patient"]),
                "clinician_id": str(clinic["clinician"]),
                "analysis_id": str(analysis["id"]),
                "severity": "high",
                "message": "High-risk check-in needs review",
            },
        )
        assert other_patient is not None

    data = (
        await api_client.get("/api/patients", headers=bearer(make_token(clinic["clinician"])))
    ).json()
    assert data["items"][0]["open_alerts"] == 1

    # Acknowledging clears the badge.
    alerts = (
        await api_client.get("/api/alerts", headers=bearer(make_token(clinic["clinician"])))
    ).json()
    await api_client.post(
        f"/api/alerts/{alerts[0]['alert_id']}/acknowledge",
        headers=bearer(make_token(clinic["clinician"])),
    )
    data = (
        await api_client.get("/api/patients", headers=bearer(make_token(clinic["clinician"])))
    ).json()
    assert data["items"][0]["open_alerts"] == 0


async def test_a_patient_cannot_use_the_roster(api_client, make_token, clinic) -> None:
    response = await api_client.get("/api/patients", headers=bearer(make_token(clinic["patient"])))
    assert response.status_code == 403


# --- trend --------------------------------------------------------------------------


async def test_trend_returns_points_within_the_window(api_client, make_token, clinic) -> None:
    now = datetime.now(UTC)
    recent = await seed_checkin(
        clinic["patient"], transcript="recent", mood=4, when=now - timedelta(days=2)
    )
    await seed_checkin(clinic["patient"], transcript="old", mood=8, when=now - timedelta(days=40))

    trend = (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/trend?days=14",
            headers=bearer(make_token(clinic["clinician"])),
        )
    ).json()
    assert trend["days"] == 14
    assert [p["checkin_id"] for p in trend["points"]] == [recent]
    assert trend["points"][0]["mood_score"] == 4
    assert trend["points"][0]["risk"] == "moderate"
    assert trend["missing_analysis"] == 0


async def test_trend_counts_risk_levels(api_client, make_token, clinic) -> None:
    now = datetime.now(UTC)
    await seed_checkin(clinic["patient"], transcript="a", risk="high", when=now - timedelta(days=1))
    await seed_checkin(
        clinic["patient"], transcript="b", risk="medium", when=now - timedelta(days=1)
    )
    await seed_checkin(clinic["patient"], transcript="c", risk="low", when=now - timedelta(days=1))

    trend = (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/trend?days=7",
            headers=bearer(make_token(clinic["clinician"])),
        )
    ).json()
    assert trend["high_count"] == 1
    assert trend["moderate_count"] == 1
    assert len(trend["points"]) == 3


async def test_trend_for_an_unconsented_patient_is_404(api_client, make_token, clinic) -> None:
    response = await api_client.get(
        f"/api/patients/{clinic['stranger']}/trend",
        headers=bearer(make_token(clinic["clinician"])),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "patient_not_found"


@pytest.mark.parametrize("days", ["0", "-1", "181"])
async def test_trend_window_is_validated(api_client, make_token, clinic, days) -> None:
    response = await api_client.get(
        f"/api/patients/{clinic['patient']}/trend?days={days}",
        headers=bearer(make_token(clinic["clinician"])),
    )
    assert response.status_code == 422


# --- check-in detail -----------------------------------------------------------------


async def test_detail_exposes_the_verified_evidence_quote(api_client, make_token, clinic) -> None:
    quote = "I keep crying in the library"
    checkin_id = await seed_checkin(
        clinic["patient"], transcript=f"{quote} but I am safe at home", evidence=quote
    )
    detail = (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/checkins/{checkin_id}",
            headers=bearer(make_token(clinic["clinician"])),
        )
    ).json()

    assert detail["transcript"] == f"{quote} but I am safe at home"
    assert detail["evidence_quote"] == quote
    assert detail["risk"] == "moderate"
    assert detail["mood_score"] == 3
    assert detail["emotions"] == ["sad", "tired"]
    assert detail["symptoms"]["sleep"] == 3
    assert detail["symptoms"]["appetite"] is None
    assert detail["model"] == "test/model"
    # The UI draws the banner from this field, so it must reflect the stored final risk.
    assert detail["risk_source"] == "both"
    assert detail["confidence"] == "medium"


async def test_detail_is_not_reachable_across_consent(api_client, make_token, clinic) -> None:
    checkin_id = await seed_checkin(clinic["stranger"], transcript="private")
    response = await api_client.get(
        f"/api/patients/{clinic['stranger']}/checkins/{checkin_id}",
        headers=bearer(make_token(clinic["clinician"])),
    )
    assert response.status_code == 404
    assert "private" not in response.text


async def test_detail_after_revocation_is_gone(api_client, make_token, clinic) -> None:
    checkin_id = await seed_checkin(clinic["patient"], transcript="was visible")
    headers = bearer(make_token(clinic["clinician"]))
    assert (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/checkins/{checkin_id}", headers=headers
        )
    ).status_code == 200

    await api_client.request(
        "DELETE",
        f"/api/consent/{clinic['clinician']}",
        headers=bearer(make_token(clinic["patient"])),
    )
    assert (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/checkins/{checkin_id}", headers=headers
        )
    ).status_code == 404


async def test_detail_of_a_deleted_checkin_is_404(api_client, make_token, clinic) -> None:
    checkin_id = await seed_checkin(clinic["patient"], transcript="deleting me")
    await api_client.delete(
        f"/api/checkins/{checkin_id}", headers=bearer(make_token(clinic["patient"]))
    )
    response = await api_client.get(
        f"/api/patients/{clinic['patient']}/checkins/{checkin_id}",
        headers=bearer(make_token(clinic["clinician"])),
    )
    assert response.status_code == 404


async def test_detail_of_a_checkin_without_analysis(api_client, make_token, clinic) -> None:
    async with service_client() as db:
        row = await db.insert(
            "checkins",
            {
                "patient_id": str(clinic["patient"]),
                "transcript": "no model output",
                "analysis_status": "analysis_failed",
            },
        )
    detail = (
        await api_client.get(
            f"/api/patients/{clinic['patient']}/checkins/{row['id']}",
            headers=bearer(make_token(clinic["clinician"])),
        )
    ).json()
    assert detail["status"] == "analysis_failed"
    assert detail["summary"] is None
    assert detail["risk"] is None
    assert detail["evidence_quote"] is None
    assert detail["mood_score"] is None
