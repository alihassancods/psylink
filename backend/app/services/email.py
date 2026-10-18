"""Email alerts through Resend, and the rule about what may be put inside them.

Two constraints shape this module:

* **No patient content.** Not the transcript, not the model's summary, not the evidence quote.
  Email is not a secure channel and the recipient list can drift; the message says only that a
  high-risk check-in needs review and where to look. Anything clinical stays in the dashboard,
  behind RLS.
* **Absence of configuration is not a failure.** Without `RESEND_API_KEY` and `ALERT_EMAIL_FROM`,
  the function reports "skipped" and the dashboard alert still exists. A missing mail provider
  must never be the reason a check-in 500s on a patient.

Resend is called over its REST endpoint with httpx — already a dependency — rather than adding
an SDK for one POST.
"""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10.0

SUBJECT = "Bridge: a high-risk check-in needs review"


def build_body(recipient_name: str | None, patient_name: str | None, dashboard_path: str) -> str:
    """Compose the message. `patient_name` is a display name only — never their words."""
    who = patient_name or "A patient"
    hello = f"Hi {recipient_name}," if recipient_name else "Hello,"
    return (
        f"{hello}\n\n"
        f"{who} just filed a check-in that Bridge rated high risk.\n\n"
        "Nothing about what they said is in this email. Read the analysis, and the patient, "
        f"in the dashboard: {dashboard_path}\n\n"
        "If you cannot reach them and you believe they are in danger, follow your local "
        "escalation procedure.\n\n"
        "-- Bridge (automated alert; please do not reply to this message)"
    )


def email_configured() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key and settings.alert_email_from)


async def send_alert_email(*, to: str, subject: str, body: str) -> bool:
    """Send one alert email. Returns whether it went out.

    Never raises: the caller has already stored a database alert, and the patient's request is
    long finished. Failures are logged by status and exception class, and no message body is
    ever logged.
    """
    settings = get_settings()
    if not email_configured():
        logger.info("alert email skipped: Resend is not configured")
        return False

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.alert_email_from,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                },
            )
    except Exception as exc:
        logger.warning("alert email failed: %s", type(exc).__name__)
        return False

    if response.status_code >= 300:
        # Resend's error body can echo the request; status code is enough to diagnose.
        logger.warning("alert email rejected with status %s", response.status_code)
        return False
    logger.info("alert email sent to a clinician")
    return True
