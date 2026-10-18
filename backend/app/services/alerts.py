"""Writing rows that a patient's own role is not allowed to write.

``analyses`` and ``alerts`` are deliberately ``select``-only for ``authenticated``: a patient
must never be able to set their own risk level, and only the pipeline raises alerts. Both
therefore go through ``service_client()``, which bypasses row-level security, so this module
owns every column it writes and takes no free-form input from a request.

Nothing here is logged: analysis text is patient content. The alert *message* is written by
this module, never quoted from the transcript, so a clinician's inbox cannot leak the words
the patient spoke into a third-party transcription service.
"""

import logging

from app.services.analysis.schemas import Analysis, AnalysisOutcome
from app.services.db import service_client

logger = logging.getLogger(__name__)

#: App risk wording -> the `public.risk_level` enum the schema stores.
DB_RISK: dict[str, str] = {"low": "low", "moderate": "medium", "high": "high"}

#: Deliberately generic. The detail lives in the analysis row, not in an inbox preview.
ALERT_MESSAGE = "High-risk check-in needs review"


async def store_analysis(
    *,
    patient_id: str,
    checkin_id: str,
    outcome: AnalysisOutcome,
) -> str | None:
    """Persist the model's reading of one check-in. Returns the new ``analyses.id``.

    Only an outcome that produced a usable analysis gets a row: ``analysis_failed`` is a
    check-in state, not an analysis, and inventing a ``risk='low'`` row for it would be the
    one genuinely wrong thing to record.
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


async def raise_high_risk_alert(patient_id: str, analysis_id: str | None) -> int:
    """Notify every clinician holding an active consent for this patient.

    Idempotent by design: an existing unacknowledged alert for the same analysis is left
    alone, so a retried request cannot pile up identical pages.
    """
    async with service_client() as db:
        clinicians = await db.fetch(
            """
            select c.clinician_id
            from public.consents c
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
        raised = 0
        for clinician in clinicians:
            await db.insert(
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
            raised += 1
    # Counts and ids only — never the transcript, the summary, or the evidence quote.
    logger.info("alerts raised: %d (patient=%s)", raised, patient_id)
    return raised
