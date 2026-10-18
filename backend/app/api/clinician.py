"""Clinician-facing reads: the roster, one patient's trend, and one check-in in full.

Every route here is a *read through the caller's own identity*. There is no `if not clinician:
raise` shortcut guarding the data, because row-level security already decides which rows exist
for this user: `profiles_select_consented`, `checkins_read_consented`, `analyses_read_consented`
and `alerts_read_assigned` all consult `app.has_active_consent`. The consequences are the ones
that matter for a mental-health tool:

* A clinician with no consent sees an empty list, not an error — nothing is leaked about
  whether a given patient exists.
* Revoking consent empties all three views at once, including history, with no cache to
  invalidate in this process.
* The risk level shown is the pipeline's floor-adjusted `final_risk`, never something a caller
  could have written: `analyses` is insert- and update-Forbidden for `authenticated`.

Clinician routes are deliberately read-only. The one write a clinician gets is acknowledging an
alert, which lives in :mod:`app.api.alerts`.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.errors import api_error
from app.core.deps import CurrentUser, require_role
from app.services.db import user_client

router = APIRouter(prefix="/api/patients", tags=["clinician"])

#: App wording <-> the `risk_level` enum. 'medium' in the schema is 'moderate' to people.
DB_RISK_READ: dict[str, str] = {"low": "low", "medium": "moderate", "high": "high"}


class PatientSummary(BaseModel):
    patient_id: UUID
    display_name: str | None
    consent_granted_at: datetime
    last_checkin_at: datetime | None
    last_risk: Literal["low", "moderate", "high"] | None
    last_summary: str | None
    open_alerts: int


class PatientPage(BaseModel):
    items: list[PatientSummary]
    total: int


class TrendPoint(BaseModel):
    checkin_id: UUID
    created_at: datetime
    mood_score: int | None
    risk: Literal["low", "moderate", "high"] | None
    risk_source: Literal["keyword", "llm", "both", "fallback"] | None
    summary: str | None


class Trend(BaseModel):
    patient_id: UUID
    days: int
    points: list[TrendPoint]
    high_count: int
    moderate_count: int
    missing_analysis: int


class CheckinDetail(BaseModel):
    checkin_id: UUID
    patient_id: UUID
    created_at: datetime
    transcript: str | None
    note: str | None
    status: Literal["pending", "analyzed", "analysis_failed"]
    model: str | None
    summary: str | None
    risk: Literal["low", "moderate", "high"] | None
    risk_source: str | None
    confidence: str | None
    evidence_quote: str | None
    mood_score: int | None
    emotions: list[str]
    symptoms: dict[str, int | None]


@router.get("", response_model=PatientPage)
async def list_patients(
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
    limit: int = Query(default=100, ge=1, le=200),
) -> PatientPage:
    """Everyone who currently shares data with this clinician, newest concern first."""
    async with user_client(user.token) as db:
        rows = await db.fetch(
            """
            select p.id as patient_id,
                   p.display_name,
                   c.granted_at,
                   (select max(x.created_at) from public.checkins x
                     where x.patient_id = p.id) as last_checkin_at,
                   (select y.risk from public.analyses y
                    where y.patient_id = p.id
                    order by y.created_at desc limit 1) as last_risk,
                   (select y.summary from public.analyses y
                    where y.patient_id = p.id
                    order by y.created_at desc limit 1) as last_summary,
                   (select count(*) from public.alerts a
                    where a.patient_id = p.id and a.clinician_id = :me
                      and a.acknowledged_at is null) as open_alerts
            from public.consents c
            join public.profiles p on p.id = c.patient_id
            where c.clinician_id = :me
              and c.revoked_at is null
            order by open_alerts desc, last_checkin_at desc nulls last, p.display_name
            limit :limit
            """,
            me=str(user.id),
            limit=limit,
        )
        total = await db.scalar(
            "select count(*) from public.consents where clinician_id = :me and revoked_at is null",
            me=str(user.id),
        )

    items = [
        PatientSummary(
            patient_id=row["patient_id"],
            display_name=row["display_name"],
            consent_granted_at=row["granted_at"],
            last_checkin_at=row["last_checkin_at"],
            last_risk=DB_RISK_READ.get(row["last_risk"]) if row["last_risk"] else None,
            last_summary=row["last_summary"],
            open_alerts=int(row["open_alerts"]),
        )
        for row in rows
    ]
    return PatientPage(items=items, total=int(total or 0))


@router.get("/{patient_id}/trend", response_model=Trend)
async def patient_trend(
    patient_id: UUID,
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
    days: int = Query(default=14, ge=1, le=180),
) -> Trend:
    """The last `days` of check-ins for one patient, with the analysis behind each.

    A patient who never consented (or revoked) produces an empty `points` list, and the route
    cannot tell that apart from a patient with no check-ins yet — which is the intended shape:
    no existence leak.
    """
    async with user_client(user.token) as db:
        # Existence check that is itself governed by RLS: an unconsented patient has no row here.
        visible = await db.fetchrow(
            "select id from public.profiles where id = :patient_id", patient_id=str(patient_id)
        )
        if visible is None:
            raise api_error("patient_not_found", "no such patient for you", 404)

        rows = await db.fetch(
            """
            select x.id as checkin_id,
                   x.created_at,
                   a.model,
                   a.summary,
                   a.risk,
                   a.signals ->> 'mood_score' as mood_score,
                   a.signals ->> 'risk_source' as risk_source
            from public.checkins x
            left join lateral (
                select y.summary, y.risk, y.model, y.signals
                from public.analyses y
                where y.checkin_id = x.id
                order by y.created_at desc
                limit 1
            ) a on true
            where x.patient_id = :patient_id
              and x.created_at >= now() - make_interval(days => :days)
            order by x.created_at desc
            limit 200
            """,
            patient_id=str(patient_id),
            days=days,
        )

    points = [
        TrendPoint(
            checkin_id=row["checkin_id"],
            created_at=row["created_at"],
            mood_score=int(row["mood_score"]) if row["mood_score"] else None,
            risk=DB_RISK_READ.get(row["risk"]) if row["risk"] else None,
            risk_source=row["risk_source"],
            summary=row["summary"],
        )
        for row in rows
    ]
    return Trend(
        patient_id=patient_id,
        days=days,
        points=points,
        high_count=sum(1 for p in points if p.risk == "high"),
        moderate_count=sum(1 for p in points if p.risk == "moderate"),
        missing_analysis=sum(1 for p in points if p.risk is None),
    )


@router.get("/{patient_id}/checkins/{checkin_id}", response_model=CheckinDetail)
async def checkin_detail(
    patient_id: UUID,
    checkin_id: UUID,
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
) -> CheckinDetail:
    """One check-in with its transcript, the model's summary, and the verified evidence quote.

    The evidence is shown exactly as stored: the pipeline already dropped any quote that was
    not a verbatim substring of the transcript, so a clinician reading it knows the patient
    said those words. That is the difference between a lead and a hallucination.
    """
    async with user_client(user.token) as db:
        row = await db.fetchrow(
            """
            select x.id as checkin_id, x.patient_id, x.created_at, x.transcript, x.note,
                   x.analysis_status, a.model, a.summary, a.signals, a.risk
            from public.checkins x
            left join lateral (
                select y.model, y.summary, y.signals, y.risk
                from public.analyses y
                where y.checkin_id = x.id
                order by y.created_at desc
                limit 1
            ) a on true
            where x.id = :checkin_id and x.patient_id = :patient_id
            """,
            checkin_id=str(checkin_id),
            patient_id=str(patient_id),
        )
    if row is None:
        raise api_error("checkin_not_found", "no such check-in for you", 404)

    signals = row["signals"] if isinstance(row["signals"], dict) else {}
    symptoms = signals.get("symptoms") if isinstance(signals.get("symptoms"), dict) else {}
    emotions = signals.get("emotions") if isinstance(signals.get("emotions"), list) else []
    mood = signals.get("mood_score")

    return CheckinDetail(
        checkin_id=row["checkin_id"],
        patient_id=row["patient_id"],
        created_at=row["created_at"],
        transcript=row["transcript"],
        note=row["note"],
        status=row["analysis_status"],
        model=row["model"],
        summary=row["summary"],
        # The banner reads these three. `risk` is the pipeline's floor-adjusted final level as
        # stored, and `risk_source` says whether the keyword screen, the model, both, or the
        # fail-safe produced it — which is how a clinician tells a real page from a fallback.
        risk=DB_RISK_READ.get(row["risk"]) if row["risk"] else None,
        risk_source=signals.get("risk_source"),
        confidence=signals.get("confidence"),
        evidence_quote=signals.get("risk_evidence"),
        mood_score=int(mood) if isinstance(mood, (int, str)) and str(mood).isdigit() else None,
        emotions=[str(e) for e in emotions],
        symptoms={str(k): (int(v) if isinstance(v, int) else None) for k, v in symptoms.items()},
    )
