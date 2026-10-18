"""Profile onboarding and self-editing — the piece signup was missing.

A Supabase auth user alone is not a Psylink user: every role check reads the ``profiles``
row. Before this router, a signup with email confirmation enabled (or an account provisioned
any other way) signed in and hit a dead end: the row had to exist, and nothing created it.

* ``POST /api/profiles/me`` creates the caller's own profile, always as a **patient** — the
  ``profiles_insert_self`` RLS policy is the enforcement, not this code. Clinician profiles
  stay a deliberate act by a care service (seed script or service-role API).
* ``POST /api/profiles/me/update`` renames the caller's own profile (any role).

Both answer with the same shape as ``GET /auth/me`` so the client's session read is one
request away after provisioning.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.errors import api_error
from app.core.deps import AuthIdentityDependency
from app.services.db import user_client

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

#: The only role a self-service caller can ever have; mirrored by the RLS WITH CHECK clause.
_SELF_SERVICE_ROLE = "patient"


class ProfileOut(BaseModel):
    """The same identity ``GET /auth/me`` returns."""

    id: UUID
    role: str
    display_name: str | None


class ProfileNameIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


async def _my_row(identity, columns: str = "id, role, display_name"):
    async with user_client(identity.token) as db:
        return await db.fetch(
            f"select {columns} from public.profiles where id = cast(:me as uuid)",
            me=str(identity.id),
        )


@router.post("/me", response_model=ProfileOut)
async def create_my_profile(identity: AuthIdentityDependency, body: ProfileNameIn) -> ProfileOut:
    """Bootstrap the signed-in account's own patient profile.

    Idempotency is refusal, not silent success: a second call gets 409 so the client can
    tell "just created" from "already provisioned elsewhere" and re-read ``/auth/me``.
    """
    name = body.display_name.strip()
    if not name:
        raise api_error("display_name_required", "A display name is required.", 422)

    if await _my_row(identity):
        raise api_error("profile_exists", "This account already has a Psylink profile.", 409)

    async with user_client(identity.token) as db:
        rows = await db.fetch(
            """
            insert into public.profiles (id, role, display_name)
            values (cast(:id as uuid), cast(:role as public.user_role), cast(:name as text))
            returning id, role, display_name
            """,
            id=str(identity.id),
            role=_SELF_SERVICE_ROLE,
            name=name,
        )

    if not rows:  # pragma: no cover - RLS raises rather than dropping the row
        raise api_error("profile_not_stored", "Your profile could not be created.", 500)

    row = rows[0]
    return ProfileOut(id=row["id"], role=str(row["role"]), display_name=row["display_name"])


@router.post("/me/update", response_model=ProfileOut)
async def update_my_profile(identity: AuthIdentityDependency, body: ProfileNameIn) -> ProfileOut:
    """Rename the caller's own profile. Only the name changes; the role column is untouched."""
    name = body.display_name.strip()
    if not name:
        raise api_error("display_name_required", "A display name is required.", 422)

    async with user_client(identity.token) as db:
        changed = await db.update(
            "profiles",
            {"display_name": name},
            where="id = cast(:me as uuid)",
            params={"me": str(identity.id)},
        )

    if changed == 0:
        raise api_error("profile_not_found", "This account has no Psylink profile yet.", 404)

    rows = await _my_row(identity)
    row = rows[0]
    return ProfileOut(id=row["id"], role=str(row["role"]), display_name=row["display_name"])
