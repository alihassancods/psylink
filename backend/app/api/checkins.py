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
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field, model_validator

from app.api.errors import api_error
from app.core.deps import CurrentUser, require_role
from app.services.alerts import raise_high_risk_alert, store_analysis
from app.services.analysis.pipeline import analyze_checkin
from app.services.analysis.schemas import Analysis, AnalysisOutcome, RiskLevel, RiskSource
from app.services.db import service_client, user_client

logger = logging.getLogger(__name__)

#: Schema enum values for `analyses.risk`, read back into the app's wording.
DB_RISK_READ: dict[str, str] = {"low": "low", "medium": "moderate", "high": "high"}

CheckinStatus = Literal["pending", "analyzed", "analysis_failed"]

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
    status: CheckinStatus
    analysis: Analysis | None
    final_risk: RiskLevel
    risk_source: RiskSource
    show_crisis_resources: bool


def text_to_analyse(payload: CheckinIn) -> str:
    """The approved transcript is what gets analysed; a typed note is appended when present."""
    return "\n".join(
        part.strip() for part in (payload.transcript, payload.note) if part and part.strip()
    )


#: Database errors are reported by exception class and nothing else. SQLAlchemy formats a
#: failed statement as ``... [SQL: ...] [parameters: (...)]``, and the bound parameters here
#: are the patient's own words — so even a truncated message is a leak. The class name plus
#: the request context is enough to diagnose; the transcript never leaves the row.
def _db_failure(exc: BaseException) -> str:
    return type(exc).__name__


async def _alert_if_high(
    outcome: AnalysisOutcome, patient_id: UUID, analysis_id: str | None
) -> None:
    """Background task: must not raise, because the patient already has their response."""
    if outcome.final_risk != "high":
        return
    try:
        await raise_high_risk_alert(str(patient_id), analysis_id)
    except Exception as exc:  # alerting failure must never corrupt a stored check-in
        logger.error("could not raise a high-risk alert: %s", _db_failure(exc))


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
    #    A failure here is reported by exception class only: this is the statement that
    #    binds the patient's words, and SQLAlchemy would otherwise echo them in its error.
    try:
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
    except Exception as exc:
        logger.error("could not store the check-in: %s", _db_failure(exc))
        raise api_error(
            "checkin_not_stored", "check-in could not be stored", status_code=500
        ) from exc
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
    except Exception as exc:  # analysis row is secondary; the check-in is the thing that must exist
        analysis_id = None
        logger.error("could not store the analysis row: %s", _db_failure(exc))

    status_value: Literal["analyzed", "analysis_failed"] = (
        "analyzed" if outcome.analysis is not None else "analysis_failed"
    )
    try:
        async with user_client(user.token) as db:
            await db.update(
                "checkins",
                {"analysis_status": status_value},
                where="id = :checkin_id and patient_id = :patient_id",
                params={"checkin_id": str(checkin_id), "patient_id": str(user.id)},
            )
    except Exception as exc:  # the check-in is stored either way; record why it stayed pending
        logger.error("could not update check-in status: %s", _db_failure(exc))

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


# --- patient history: list and delete ------------------------------------------------
#
# The list joins the newest analysis so a patient sees one row per check-in with whatever the
# pipeline concluded. `risk` is read from the analysis row, which only the service can write —
# a patient cannot talk their way to a lower risk level by editing anything here.


class CheckinSummary(BaseModel):
    checkin_id: UUID
    created_at: datetime
    transcript: str | None
    note: str | None
    status: CheckinStatus
    risk: RiskLevel | None
    summary: str | None


class CheckinPage(BaseModel):
    items: list[CheckinSummary]
    limit: int
    offset: int


@router.get("", response_model=CheckinPage)
async def list_checkins(
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> CheckinPage:
    """This patient's check-ins, newest first, each with its analysis if one exists."""
    async with user_client(user.token) as db:
        rows = await db.fetch(
            """
            select c.id, c.created_at, c.transcript, c.note, c.analysis_status,
                   a.risk, a.summary
            from public.checkins c
            left join lateral (
                select x.risk, x.summary
                from public.analyses x
                where x.checkin_id = c.id
                order by x.created_at desc
                limit 1
            ) a on true
            where c.patient_id = :patient_id
            order by c.created_at desc
            limit :limit offset :offset
            """,
            patient_id=str(user.id),
            limit=limit,
            offset=offset,
        )
    items = [
        CheckinSummary(
            checkin_id=row["id"],
            created_at=row["created_at"],
            transcript=row["transcript"],
            note=row["note"],
            status=row["analysis_status"],
            # The column stores 'medium'; the API speaks 'moderate'. One mapping, both ways.
            risk=DB_RISK_READ.get(row["risk"]) if row["risk"] else None,
            summary=row["summary"],
        )
        for row in rows
    ]
    return CheckinPage(items=items, limit=limit, offset=offset)


@router.delete("/{checkin_id}", status_code=204)
async def delete_checkin(
    checkin_id: UUID,
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> None:
    """Delete one of the patient's own check-ins — and the analysis derived from it.

    The analysis is removed too, through the service identity, because the patient cannot write
    that table and because leaving a clinician-facing summary behind after the patient withdrew
    the source would be the wrong default. Any alert keeps its row: it records that a clinician
    was paged, which stays true.
    """
    # Ownership is settled first, by the patient's own identity: if the row is not theirs, RLS
    # matches nothing and there is nothing left to delete.
    async with user_client(user.token) as db:
        owned = await db.fetchrow(
            "select id from public.checkins where id = :checkin_id and patient_id = :patient_id",
            checkin_id=str(checkin_id),
            patient_id=str(user.id),
        )
    if owned is None:
        raise api_error("checkin_not_found", "no check-in with that id", 404)

    # Then the analysis — *before* the check-in goes. `analyses.checkin_id` is
    # `on delete set null`, so deleting the check-in first would null the link out from under
    # this query and leave an orphaned summary of words the patient just withdrew, still
    # readable by a consented clinician. Alerts keep their own rows either way.
    async with service_client() as db:
        await db.execute(
            "delete from public.analyses where checkin_id = :checkin_id",
            checkin_id=str(checkin_id),
        )

    async with user_client(user.token) as db:
        await db.execute(
            "delete from public.checkins where id = :checkin_id and patient_id = :patient_id",
            checkin_id=str(checkin_id),
            patient_id=str(user.id),
        )
