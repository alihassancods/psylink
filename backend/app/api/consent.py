"""``/api/link`` and ``/api/consent`` — who may see a patient's data, and for how long.

A clinician mints a short code (``POST /api/link``); the patient redeems it
(``POST /api/consent``), and that insert is the *only* thing that creates access. Two
properties are load-bearing:

* The code is stored as a hash and returned exactly once, so a database leak yields expired
  hashes rather than working links, and a clinician cannot be spied on through their codes.
* Consuming a code grants nothing by itself. ``app.redeem_invite`` returns the clinician id;
  the consent row is still inserted through the patient's own RLS policy, so nobody but the
  patient can ever share the patient's data.

Revoking stamps ``revoked_at`` instead of deleting: the grant history survives, and every
policy that consults consent stops showing history at the same moment (see
``tests/rls/test_clinician_consent.py``).
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.errors import api_error
from app.core.deps import CurrentUser, require_role
from app.services.db import user_client

logger = logging.getLogger(__name__)

#: Codes are short because a human reads them aloud or types them on a phone.
CODE_BYTES = 5  # -> 10 hex characters
CODE_TTL = timedelta(hours=24)
MAX_CODE_CHARS = 32

router = APIRouter(tags=["consent"])


class InviteCreated(BaseModel):
    """The plaintext `code` is present in this response only — the database never sees it."""

    invite_id: UUID
    code: str
    expires_at: datetime


class InviteRow(BaseModel):
    invite_id: UUID
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_by: UUID | None


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=MAX_CODE_CHARS)


class ConsentRow(BaseModel):
    consent_id: UUID
    clinician_id: UUID
    clinician_name: str | None
    granted_at: datetime


class Revoked(BaseModel):
    consent_id: UUID
    revoked_at: datetime


def generate_code() -> str:
    """A read-out-loud code: lowercase hex, no ambiguous characters to confuse."""
    return secrets.token_hex(CODE_BYTES)


def normalize_code(code: str) -> str:
    """Tolerate a patient typing the code with spaces, dashes, or capitals."""
    return "".join(ch for ch in code.strip().lower() if ch.isalnum())


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


# --- clinician side ------------------------------------------------------------------


@router.post("/api/link", response_model=InviteCreated, status_code=201)
async def create_invite(
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
) -> InviteCreated:
    """Mint a single-use invite code, valid for 24 hours."""
    code = generate_code()
    expires_at = datetime.now(UTC) + CODE_TTL
    async with user_client(user.token) as db:
        row = await db.insert(
            "invites",
            {
                "clinician_id": str(user.id),
                "code_hash": hash_code(code),
                "expires_at": expires_at,
            },
            returning=("id", "expires_at"),
        )
    if row is None:  # pragma: no cover - RLS raises instead of dropping the row
        raise api_error("invite_not_stored", "invite could not be created", 500)

    # Only the hash is stored, so this response is the code's one and only appearance.
    return InviteCreated(invite_id=row["id"], code=code, expires_at=row["expires_at"])


@router.get("/api/link", response_model=list[InviteRow])
async def list_invites(
    user: Annotated[CurrentUser, Depends(require_role("clinician"))],
) -> list[InviteRow]:
    """This clinician's invites. Codes are not recoverable — they were never stored."""
    async with user_client(user.token) as db:
        rows = await db.select(
            "invites",
            columns=("id", "created_at", "expires_at", "used_at", "used_by"),
            where="clinician_id = :me",
            params={"me": str(user.id)},
            order_by="created_at desc",
            limit=50,
        )
    return [
        InviteRow(
            invite_id=row["id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            used_at=row["used_at"],
            used_by=row["used_by"],
        )
        for row in rows
    ]


# --- patient side --------------------------------------------------------------------


@router.get("/api/consent", response_model=list[ConsentRow])
async def list_consents(
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> list[ConsentRow]:
    """Who currently sees this patient's data — the "sharing" panel, and 1.7's precondition."""
    async with user_client(user.token) as db:
        rows = await db.fetch(
            """
            select c.id as consent_id, c.clinician_id, p.display_name, c.granted_at
            from public.consents c
            left join public.profiles p on p.id = c.clinician_id
            where c.patient_id = :patient_id
              and c.revoked_at is null
            order by c.granted_at desc
            """,
            patient_id=str(user.id),
        )
    return [
        ConsentRow(
            consent_id=row["consent_id"],
            clinician_id=row["clinician_id"],
            clinician_name=row["display_name"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


@router.post("/api/consent", response_model=ConsentRow, status_code=201)
async def redeem_invite(
    payload: RedeemIn,
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> ConsentRow:
    """Turn a clinician's code into an active consent for this patient."""
    code = normalize_code(payload.code)
    if len(code) != CODE_BYTES * 2:
        raise api_error("invite_invalid", "that code is not valid")

    async with user_client(user.token) as db:
        clinician_id = await db.scalar(
            "select app.redeem_invite(:code_hash)", code_hash=hash_code(code)
        )
        if clinician_id is None:
            # Expired, already used, unknown, or this very clinician's own attempt.
            raise api_error("invite_invalid", "that code is expired or already used")

        # An invite is not a second grant: if the pair is already linked, report that link.
        existing = await db.fetchrow(
            """
            select c.id, c.clinician_id, p.display_name, c.granted_at
            from public.consents c
            left join public.profiles p on p.id = c.clinician_id
            where c.patient_id = :patient_id and c.clinician_id = :clinician_id
              and c.revoked_at is null
            """,
            patient_id=str(user.id),
            clinician_id=str(clinician_id),
        )
        if existing is not None:
            return ConsentRow(
                consent_id=existing["id"],
                clinician_id=existing["clinician_id"],
                clinician_name=existing["display_name"],
                granted_at=existing["granted_at"],
            )

        row = await db.insert(
            "consents",
            {"patient_id": str(user.id), "clinician_id": str(clinician_id)},
            returning=("id", "clinician_id", "granted_at"),
        )
        if row is None:  # pragma: no cover - the patient's own insert policy cannot miss
            raise api_error("consent_not_stored", "consent could not be recorded", 500)
        named = await db.fetchrow(
            "select display_name from public.profiles where id = :clinician_id",
            clinician_id=str(row["clinician_id"]),
        )

    logger.info("consent granted for a patient by invite code")  # ids and codes are not logged
    return ConsentRow(
        consent_id=row["id"],
        clinician_id=row["clinician_id"],
        clinician_name=named["display_name"] if named else None,
        granted_at=row["granted_at"],
    )


@router.delete("/api/consent/{clinician_id}", response_model=Revoked)
async def revoke_consent(
    clinician_id: UUID,
    user: Annotated[CurrentUser, Depends(require_role("patient"))],
) -> Revoked:
    """Withdraw access. Revoking hides the history as well as future rows."""
    async with user_client(user.token) as db:
        now = datetime.now(UTC)
        updated = await db.update(
            "consents",
            {"revoked_at": now},
            where="patient_id = :patient_id and clinician_id = :clinician_id "
            "and revoked_at is null",
            params={"patient_id": str(user.id), "clinician_id": str(clinician_id)},
        )
        if not updated:
            raise api_error("consent_not_found", "no active consent with that clinician", 404)
        row = await db.fetchrow(
            "select id, revoked_at from public.consents "
            "where patient_id = :patient_id and clinician_id = :clinician_id "
            "order by granted_at desc limit 1",
            patient_id=str(user.id),
            clinician_id=str(clinician_id),
        )
    return Revoked(consent_id=row["id"], revoked_at=row["revoked_at"])


# --- shared helper for other routes ----------------------------------------------------


async def has_active_consent(user: CurrentUser) -> bool:
    """Does this patient have at least one live consent? Transcription depends on it."""
    async with user_client(user.token) as db:
        row = await db.fetchrow(
            "select 1 as present from public.consents "
            "where patient_id = :patient_id and revoked_at is null limit 1",
            patient_id=str(user.id),
        )
    return row is not None
