"""Writing rows that a patient's own role is not allowed to write, and telling humans about them.

``analyses`` and ``alerts`` are deliberately ``select``-only for ``authenticated``: a patient
must never be able to set their own risk level, and only the pipeline raises alerts. Both
therefore go through ``service_client()``, which bypasses row-level security, so this module
owns every column it writes and takes no free-form input from a request.

Nothing here is logged: analysis text is patient content. The alert *message* is written by this
module, never quoted from the transcript, so a clinician's inbox cannot leak the words the
patient spoke into a third-party transcription service. The email body obeys the same rule — see
:mod:`app.services.email`.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.services.analysis.schemas import Analysis, AnalysisOutcome
from app.services.db import service_client
from app.services.email import SUBJECT, build_body, email_configured, send_alert_email

logger = logging.getLogger(__name__)

#: App risk wording -> the `public.risk_level` enum the schema stores.
DB_RISK: dict[str, str] = {"low": "low", "moderate": "medium", "high": "high"}

#: Deliberately generic. The detail lives in the analysis row, not in an inbox preview.
ALERT_MESSAGE = "High-risk check-in needs review"


def dashboard_link(patient_id: str, origin: str) -> str:
    """Where the clinician should look. The id is in the URL; nothing clinical is."""
    base = (origin or "").split(",")[0].strip().rstrip("/")
    return f"{base}/clinician/patients/{patient_id}"


async def store_analysis(
    *,
    patient_id: str,
    checkin_id: str,
    outcome: AnalysisOutcome,
) -> str | None:
    """Persist the model's reading of one check-in. Returns the new ``analyses.id``.

    Only an outcome that produced a usable analysis gets a row: ``analysis_failed`` is a
    check-in state, not an analysis, and inventing a ``risk='low'`` row for it would be the one
    genuinely wrong thing to record.
    """
    analysis: Analysis | None = outcome.analysis
    if analysis is None:
        return None

    signals = {
        "mood_score": analysis.mood_score,
        "emotions": analysis.emotions,
        "symptoms": analysis.symptoms.model_dump(),
        "risk_level": outcome.final_risk,
        "risk_evidence": analysis.risk_evidence,
        "confidence": analysis.confidence,
        "risk_source": outcome.risk_source,
    }

    async with service_client() as db:
        row = await db.insert(
            "analyses",
            {
                "patient_id": patient_id,
                "checkin_id": checkin_id,
                "model": outcome.model_used,
                "summary": analysis.summary,
                "risk": DB_RISK[outcome.final_risk],
                "signals": signals,
            },
            returning=("id",),
        )
    return str(row["id"]) if row else None


async def _clinicians_to_notify(
    db, patient_id: str, analysis_id: str | None
) -> list[dict[str, Any]]:
    """Clinicians with a live consent who have no open alert for this analysis yet."""
    return await db.fetch(
        """
        select c.clinician_id, p.email, p.display_name as clinician_name,
               coalesce(pp.display_name, 'A patient') as patient_name
        from public.consents c
        join public.profiles p on p.id = c.clinician_id
        join public.profiles pp on pp.id = c.patient_id
        where c.patient_id = :patient_id
          and c.revoked_at is null
          and not exists (
              select 1 from public.alerts a
              where a.analysis_id = :analysis_id
                and a.clinician_id = c.clinician_id
                and a.acknowledged_at is null
          )
        """,
        patient_id=patient_id,
        analysis_id=analysis_id,
    )


async def raise_high_risk_alert(
    patient_id: str,
    analysis_id: str | None,
    *,
    origin: str | None = None,
) -> int:
    """Page every clinician who currently holds consent for this patient.

    Returns the number of alert rows created. Retrying the same analysis creates nothing, so an
    impatient frontend cannot manufacture a queue of identical pages.

    Email is attempted only for rows created here, and is deduplicated per
    clinician-and-patient over ``ALERT_DEDUPE_HOURS``.
    """
    settings = get_settings()
    link_origin = origin or settings.frontend_origin

    async with service_client() as db:
        clinicians = await _clinicians_to_notify(db, patient_id, analysis_id)
        created: list[dict[str, Any]] = []
        for clinician in clinicians:
            row = await db.insert(
                "alerts",
                {
                    "patient_id": patient_id,
                    "clinician_id": str(clinician["clinician_id"]),
                    "analysis_id": analysis_id,
                    "severity": "high",
                    "message": ALERT_MESSAGE,
                },
                returning=("id",),
            )
            if row is not None:
                created.append({**clinician, "alert_id": str(row["id"])})

    # Outside the transaction: a slow mail provider must not hold a database transaction open.
    for pending in created:
        await _deliver(
            alert_id=pending["alert_id"],
            clinician_id=str(pending["clinician_id"]),
            email=pending["email"],
            clinician_name=pending["clinician_name"],
            patient_id=patient_id,
            patient_name=pending["patient_name"],
            origin=link_origin,
            hours=settings.alert_dedupe_hours,
        )

    # Counts and ids only — never the transcript, the summary, or the evidence quote.
    logger.info("alerts raised: %d (patient=%s)", len(created), patient_id)
    return len(created)


async def _already_emailed(*, clinician_id: str, patient_id: str, hours: int) -> bool:
    """Was this clinician emailed about this patient inside the dedupe window?"""
    async with service_client() as db:
        value = await db.scalar(
            """
            select 1 from public.alerts
            where clinician_id = :clinician_id
              and patient_id = :patient_id
              and emailed_at is not null
              and emailed_at > now() - make_interval(hours => :hours)
            limit 1
            """,
            clinician_id=clinician_id,
            patient_id=patient_id,
            hours=hours,
        )
    return value is not None


async def _deliver(
    *,
    alert_id: str,
    clinician_id: str,
    email: str | None,
    clinician_name: str | None,
    patient_id: str,
    patient_name: str,
    origin: str,
    hours: int,
) -> bool:
    """Send this alert's email if allowed, then stamp it so the window is honest.

    Dedupe is on *delivery*, not on the row: several high check-ins in one window each keep
    their own alert so the clinician still sees the count, but only the first sends mail. Two
    alerts landing at the same instant can both send — acceptable at this scale, and the rows
    still record both.
    """
    if not email or not email_configured():
        return False

    if await _already_emailed(clinician_id=clinician_id, patient_id=patient_id, hours=hours):
        logger.info("alert email suppressed by the dedupe window")
        return False

    sent = await send_alert_email(
        to=email,
        subject=SUBJECT,
        body=build_body(clinician_name, patient_name, dashboard_link(patient_id, origin)),
    )
    if sent:
        async with service_client() as db:
            await db.update(
                "alerts",
                {"emailed_at": datetime.now(UTC)},
                where="id = :id",
                params={"id": alert_id},
            )
    return sent
