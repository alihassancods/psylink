"""``POST /api/checkins`` — store first, then analyse, so a check-in is never lost.

The order is the point:

1. insert the check-in as ``pending`` in its own committed transaction;
2. run the pipeline (it returns an outcome instead of raising, and never touches the DB);
3. record what happened — ``analyzed`` or ``analysis_failed``;
4. only then, in a background task, alert clinicians if the floor says high.

If step 2 dies mid-flight the row is still there, marked ``analysis_failed``, with the
patient's words intact. The response reports the floor-adjusted risk level rather than the
model's alone, and whether crisis resources should show.
"""

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field, model_validator

from app.api.errors import api_error
from app.core.deps import CurrentUser, require_role
from app.services.alerts import raise_high_risk_alert, store_analysis
from app.services.analysis.pipeline import analyze_checkin
from app.services.analysis.schemas import Analysis, AnalysisOutcome, RiskLevel, RiskSource
from app.services.db import user_client

logger = logging.getLogger(__name__)

#: A transcript longer than this is not a spoken check-in; the frontend caps far earlier.
MAX_TEXT_CHARS = 20_000

router = APIRouter(prefix="/api/checkins", tags=["checkins"])


class CheckinIn(BaseModel):
    """Either the approved transcript or a typed note — at least one must be present."""

    transcript: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    note: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)

    @model_validator(mode="after")
    def _something_to_analyse(self) -> CheckinIn:
        if not (self.transcript or "").strip() and not (self.note or "").strip():
            raise ValueError("transcript or note is required")
        return self


class CheckinResponse(BaseModel):
    checkin_id: UUID
    status: Literal["analyzed", "analysis_failed"]
    analysis: Analysis | None
    final_risk: RiskLevel
    risk_source: RiskSource
    show_crisis_resources: bool


def text_to_analyse(payload: CheckinIn) -> str:
    """The approved transcript is what gets analysed; a typed note is appended when present."""
    return "\n".join(
        part.strip() for part in (payload.transcript, payload.note) if part and part.strip()
    )


async def _alert_if_high(
    outcome: AnalysisOutcome, patient_id: UUID, analysis_id: str | None
) -> None:
    """Background task: must not raise, because the patient already has their response."""
    if outcome.final_risk != "high":
        return
    try:
        await raise_high_risk_alert(str(patient_id), analysis_id)
    except Exception:  # alerting failure must never corrupt a stored check-in
        logger.exception("failed to raise a high-risk alert for a stored check-in")


@router.post("", response_model=CheckinResponse, status_code=201)
async def create_checkin(
    payload: CheckinIn,
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> CheckinResponse:
    """Save one check-in, analyse it, and report the guarded risk level back."""
    text = text_to_analyse(payload)
    if not text:
        raise api_error("checkin_required", "transcript or note is required")

    source = "voice" if (payload.transcript or "").strip() else "typed"

    # 1. Persist before analysing. Its own transaction, committed when the block exits.
    async with user_client(user.token) as db:
        row = await db.insert(
            "checkins",
            {
                "patient_id": str(user.id),
                "answers": {"source": source},
                "note": (payload.note or "").strip() or None,
                "transcript": (payload.transcript or "").strip() or None,
                "analysis_status": "pending",
            },
            returning=("id",),
        )
    if row is None:  # pragma: no cover - RLS raises rather than silently dropping a row
        raise api_error("checkin_not_stored", "check-in could not be stored", status_code=500)
    checkin_id = UUID(str(row["id"]))

    # 2. Analyse. Always an outcome back, even when every model call failed.
    outcome = await analyze_checkin(text)

    # 3. Record it. The analysis row needs service rights (patients cannot write their own
    #    risk level); the status update is the patient's own row, so it uses their identity.
    #    A failure here must not strand the check-in: it is already stored, so the status
    #    update below still runs.
    try:
        analysis_id = await store_analysis(
            patient_id=str(user.id), checkin_id=str(checkin_id), outcome=outcome
        )
    except Exception:  # analysis row is secondary; the check-in is the thing that must exist
        analysis_id = None
        logger.exception("could not store the analysis row")

    status_value: Literal["analyzed", "analysis_failed"] = (
        "analyzed" if outcome.analysis is not None else "analysis_failed"
    )
    async with user_client(user.token) as db:
        await db.update(
            "checkins",
            {"analysis_status": status_value},
            where="id = :checkin_id and patient_id = :patient_id",
            params={"checkin_id": str(checkin_id), "patient_id": str(user.id)},
        )

    # 4. Alert after the patient has their answer.
    background_tasks.add_task(_alert_if_high, outcome, user.id, analysis_id)

    return CheckinResponse(
        checkin_id=checkin_id,
        status=status_value,
        analysis=outcome.analysis,
        final_risk=outcome.final_risk,
        risk_source=outcome.risk_source,
        show_crisis_resources=outcome.show_crisis_resources,
    )
