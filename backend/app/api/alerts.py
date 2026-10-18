"""``/api/alerts`` — the clinician's queue, and acknowledging a page.

Two rules:

* A clinician only ever sees alerts for patients they hold a **live** consent for. That is not
  route logic — the RLS policy `alerts_read_assigned` already joins on `app.has_active_consent`,
  so revocation empties this queue including its history, and a token for a clinician who was
  never consented returns an empty list rather than an error.
* Acknowledging stamps `acknowledged_at` and `acknowledged_by` together. The schema refuses an
  `acknowledged_at` without an author (`alerts_acknowledged_by_consistent`), so the route must
  write both — and it writes them only for a row the caller can already see, which means a
  clinician cannot acknowledge somebody else's page.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.errors import api_error
from app.core.deps import CurrentUser, require_role
from app.services.db import user_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertRow(BaseModel):
    alert_id: UUID
    patient_id: UUID
    patient_name: str | None
    severity: Literal["low", "medium", "high"]
    message: str
    created_at: datetime
    acknowledged_at: datetime | None
    analysis_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class AcknowledgeResponse(BaseModel):
    alert_id: UUID
    acknowledged_at: datetime
    acknowledged_by: UUID


@router.get("", response_model=list[AlertRow])
async def list_alerts(
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
    status: Literal["open", "all"] = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertRow]:
    """This clinician's alerts. `open` (the default) hides anything already acknowledged."""
    where = "a.clinician_id = :me" + (" and a.acknowledged_at is null" if status == "open" else "")
    async with user_client(user.token) as db:
        rows = await db.fetch(
            f"""
            select a.id as alert_id, a.patient_id, a.severity, a.message, a.created_at,
                   a.acknowledged_at, a.analysis_id, p.display_name as patient_name
            from public.alerts a
            left join public.profiles p on p.id = a.patient_id
            where {where}
            order by a.created_at desc
            limit {int(limit)}
            """,
            me=str(user.id),
        )
    return [AlertRow.model_validate(dict(row)) for row in rows]


@router.post("/{alert_id}/acknowledge", response_model=AcknowledgeResponse)
async def acknowledge_alert(
    alert_id: UUID,
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
) -> AcknowledgeResponse:
    """Mark an alert seen. Only the addressed clinician can do it, and only once."""
    now = datetime.now(UTC)
    async with user_client(user.token) as db:
        updated = await db.update(
            "alerts",
            {"acknowledged_at": now, "acknowledged_by": str(user.id)},
            where="id = :alert_id and acknowledged_at is null",
            params={"alert_id": str(alert_id)},
        )
        if not updated:
            # Either the row is not theirs to see (RLS made the update match nothing) or it is
            # already acknowledged. Both are reported the same way: nothing left to do here.
            raise api_error("alert_not_found", "no unacknowledged alert with that id for you", 404)
        row = await db.fetchrow(
            "select id, acknowledged_at, acknowledged_by from public.alerts where id = :id",
            id=str(alert_id),
        )

    return AcknowledgeResponse(
        alert_id=row["id"],
        acknowledged_at=row["acknowledged_at"],
        acknowledged_by=row["acknowledged_by"],
    )
