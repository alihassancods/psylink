"""Alert delivery: the inbox, acknowledgement, dedupe, and what an email may contain.

`send_alert_email` is stubbed at the module boundary the service actually calls, so the
assertions are about *policy* — who gets mailed, how often, and what the message says — not
about Resend's HTTP contract.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.core.config import Settings
from app.models.profile import UserRole
from app.services import alerts as alerts_module
from app.services import email as email_module
from app.services.alerts import dashboard_link, raise_high_risk_alert
from app.services.db import service_client

PATIENT_WORDS = "I want to kill myself"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch):
    """Stub the transport and record every send."""
    sent: list[dict[str, Any]] = []

    async def fake_send(*, to: str, subject: str, body: str) -> bool:
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(alerts_module, "send_alert_email", fake_send)
    return sent


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch):
    """Act as if Resend is set up, without putting a key anywhere real."""
    monkeypatch.setattr(
        email_module,
        "get_settings",
        lambda: Settings(
            _env_file=None, resend_api_key="test-key", alert_email_from="alerts@bridge.example"
        ),
    )


@pytest.fixture
async def linked(seed_profile, seed_consent) -> dict[str, Any]:
    patient = await seed_profile(role=UserRole.PATIENT, display_name="Robin")
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Chen")
    # A delivery address, because that is what a real clinician row has. Without one the
    # service correctly falls back to dashboard-only, which has its own test.
    async with service_client() as db:
        await db.update(
            "profiles",
            {"email": "chen@bridge.example"},
            where="id = :id",
            params={"id": str(clinician)},
        )
    await seed_consent(patient, clinician)
    return {"patient": patient, "clinician": clinician}


@pytest.fixture
async def analysis_row(linked) -> UUID:
    async with service_client() as db:
        checkin = await db.insert(
            "checkins", {"patient_id": str(linked["patient"]), "transcript": PATIENT_WORDS}
        )
        analysis = await db.insert(
            "analyses",
            {
                "patient_id": str(linked["patient"]),
                "checkin_id": str(checkin["id"]),
                "risk": "high",
            },
        )
    linked["checkin_id"] = checkin["id"]
    return analysis["id"]


# --- what the message says ----------------------------------------------------------


def test_body_names_nothing_clinical() -> None:
    from app.services.email import build_body

    text = build_body("Dr Chen", "Robin", dashboard_link("pat-1", "https://bridge.example"))
    assert "Dr Chen" in text and "Robin" in text
    assert "https://bridge.example/clinician/patients/pat-1" in text
    # No diagnosis language, no invented clinical content.
    for banned in ("depress", "bipolar", "disorder", "diagnos"):
        assert banned not in text.lower()


def test_dashboard_link_uses_the_first_configured_origin() -> None:
    assert dashboard_link("p1", "https://a.vercel.app, http://localhost:3000") == (
        "https://a.vercel.app/clinician/patients/p1"
    )
    assert (
        dashboard_link("p1", "https://a.vercel.app/")
        == "https://a.vercel.app/clinician/patients/p1"
    )


# --- delivery policy --------------------------------------------------------------


async def test_alert_emails_the_consented_clinician(linked, analysis_row, mail, configured) -> None:
    raised = await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    assert raised == 1
    assert len(mail) == 1
    assert mail[0]["to"]  # the clinician's address

    async with service_client() as db:
        rows = await db.select(
            "alerts", where="patient_id = :p", params={"p": str(linked["patient"])}
        )
    assert rows[0]["emailed_at"] is not None


async def test_email_never_contains_the_patient_s_words(
    linked, analysis_row, mail, configured
) -> None:
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    assert mail
    assert PATIENT_WORDS not in mail[0]["body"]
    assert "kill" not in mail[0]["body"].lower()


async def test_same_analysis_does_not_alert_twice(linked, analysis_row, mail, configured) -> None:
    assert await raise_high_risk_alert(str(linked["patient"]), str(analysis_row)) == 1
    assert await raise_high_risk_alert(str(linked["patient"]), str(analysis_row)) == 0
    assert len(mail) == 1


async def test_dedupe_window_suppresses_the_second_email(
    linked, mail, configured, monkeypatch
) -> None:
    """Two separate high check-ins in one window: two alert rows, one email."""
    monkeypatch.setattr(
        alerts_module,
        "get_settings",
        lambda: Settings(_env_file=None, alert_dedupe_hours=6, frontend_origin="http://x"),
    )
    first, second = await _two_analyses(linked["patient"])

    assert await raise_high_risk_alert(str(linked["patient"]), first) == 1
    assert await raise_high_risk_alert(str(linked["patient"]), second) == 1
    assert len(mail) == 1  # the second is deduplicated

    async with service_client() as db:
        rows = await db.select(
            "alerts", where="patient_id = :p", params={"p": str(linked["patient"])}
        )
    assert len(rows) == 2  # both are still visible in the queue
    assert sum(1 for r in rows if r["emailed_at"] is not None) == 1


async def test_a_short_window_allows_the_next_email(linked, mail, monkeypatch) -> None:
    monkeypatch.setattr(
        alerts_module,
        "get_settings",
        lambda: Settings(_env_file=None, alert_dedupe_hours=1, frontend_origin="http://x"),
    )
    monkeypatch.setattr(
        email_module,
        "get_settings",
        lambda: Settings(_env_file=None, resend_api_key="test-key", alert_email_from="a@b.example"),
    )
    first, second = await _two_analyses(linked["patient"])
    await raise_high_risk_alert(str(linked["patient"]), first)

    # Back-date the delivery stamp past the window; the next alert should mail again.
    async with service_client() as db:
        await db.update(
            "alerts",
            {"emailed_at": datetime(2020, 1, 1, tzinfo=UTC)},
            where="patient_id = :p",
            params={"p": str(linked["patient"])},
        )
    await raise_high_risk_alert(str(linked["patient"]), second)
    assert len(mail) == 2


async def test_no_configuration_means_no_email_but_still_an_alert(
    linked, analysis_row, mail, monkeypatch
) -> None:
    monkeypatch.setattr(
        email_module, "get_settings", lambda: Settings(_env_file=None, resend_api_key="")
    )
    assert await raise_high_risk_alert(str(linked["patient"]), str(analysis_row)) == 1
    assert mail == []
    async with service_client() as db:
        rows = await db.select(
            "alerts", where="patient_id = :p", params={"p": str(linked["patient"])}
        )
    assert len(rows) == 1
    assert rows[0]["emailed_at"] is None  # never claimed to have been delivered


async def test_clinician_without_an_email_gets_a_dashboard_row_only(
    mail, configured, seed_profile, seed_consent
) -> None:
    patient = await seed_profile(role=UserRole.PATIENT, display_name="No Mail")
    clinician = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Quiet")
    async with service_client() as db:
        await db.update(
            "profiles", {"email": None}, where="id = :id", params={"id": str(clinician)}
        )
    await seed_consent(patient, clinician)
    analysis = await _one_analysis(patient)

    assert await raise_high_risk_alert(str(patient), analysis) == 1
    assert mail == []


# --- the inbox route ------------------------------------------------------------


async def test_clinician_sees_and_acks_their_alert(
    api_client, make_token, linked, analysis_row, mail, configured
) -> None:
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    headers = bearer(make_token(linked["clinician"]))

    inbox = await api_client.get("/api/alerts", headers=headers)
    assert inbox.status_code == 200
    rows = inbox.json()
    assert len(rows) == 1
    assert rows[0]["severity"] == "high"
    assert rows[0]["patient_name"] == "Robin"
    assert PATIENT_WORDS not in inbox.text  # the queue never carries the transcript

    ack = await api_client.post(f"/api/alerts/{rows[0]['alert_id']}/acknowledge", headers=headers)
    assert ack.status_code == 200, ack.text
    assert ack.json()["acknowledged_by"] == str(linked["clinician"])

    assert (await api_client.get("/api/alerts", headers=headers)).json() == []
    assert len((await api_client.get("/api/alerts?status=all", headers=headers)).json()) == 1


async def test_acknowledging_twice_is_404(
    api_client, make_token, linked, analysis_row, mail, configured
) -> None:
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    headers = bearer(make_token(linked["clinician"]))
    alert_id = (await api_client.get("/api/alerts", headers=headers)).json()[0]["alert_id"]

    assert (
        await api_client.post(f"/api/alerts/{alert_id}/acknowledge", headers=headers)
    ).status_code == 200
    again = await api_client.post(f"/api/alerts/{alert_id}/acknowledge", headers=headers)
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == "alert_not_found"


async def test_a_patient_cannot_read_the_alert_queue(
    api_client, make_token, linked, analysis_row, mail, configured
) -> None:
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    response = await api_client.get("/api/alerts", headers=bearer(make_token(linked["patient"])))
    assert response.status_code == 403


async def test_unlinked_clinician_sees_nothing(
    api_client, make_token, linked, analysis_row, mail, configured, seed_profile
) -> None:
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    stranger = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr Nobody")
    response = await api_client.get("/api/alerts", headers=bearer(make_token(stranger)))
    assert response.status_code == 200
    assert response.json() == []


async def test_revoking_consent_hides_the_alert_history(
    api_client, make_token, linked, analysis_row, mail, configured
) -> None:
    """The alert existed; withdrawing access closes it, exactly as the RLS suite asserts."""
    await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))
    clinician_headers = bearer(make_token(linked["clinician"]))
    assert len((await api_client.get("/api/alerts", headers=clinician_headers)).json()) == 1

    await api_client.request(
        "DELETE",
        f"/api/consent/{linked['clinician']}",
        headers=bearer(make_token(linked["patient"])),
    )
    assert (await api_client.get("/api/alerts?status=all", headers=clinician_headers)).json() == []


async def test_email_failure_is_logged_by_class_only(
    linked, analysis_row, configured, monkeypatch, caplog
) -> None:
    async def failing_send(*, to: str, subject: str, body: str) -> bool:
        return False

    monkeypatch.setattr(alerts_module, "send_alert_email", failing_send)
    with caplog.at_level(logging.INFO):
        raised = await raise_high_risk_alert(str(linked["patient"]), str(analysis_row))

    assert raised == 1  # the alert row still exists; the patient is not affected
    async with service_client() as db:
        rows = await db.select(
            "alerts", where="patient_id = :p", params={"p": str(linked["patient"])}
        )
    assert rows[0]["emailed_at"] is None
    assert PATIENT_WORDS not in caplog.text


# --- helpers ---------------------------------------------------------------------


async def _two_analyses(patient_id: UUID) -> tuple[str, str]:
    async with service_client() as db:
        ids = []
        for _ in range(2):
            checkin = await db.insert("checkins", {"patient_id": str(patient_id)})
            analysis = await db.insert(
                "analyses",
                {"patient_id": str(patient_id), "checkin_id": str(checkin["id"]), "risk": "high"},
            )
            ids.append(str(analysis["id"]))
    return ids[0], ids[1]


async def _one_analysis(patient_id: UUID) -> str:
    async with service_client() as db:
        checkin = await db.insert("checkins", {"patient_id": str(patient_id)})
        analysis = await db.insert(
            "analyses",
            {"patient_id": str(patient_id), "checkin_id": str(checkin["id"]), "risk": "high"},
        )
    return str(analysis["id"])
