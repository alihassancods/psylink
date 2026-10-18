"""FastAPI dependencies that turn a request into an authenticated identity.

``Depends(get_current_user)`` gives any route the caller's ``CurrentUser``;
``Depends(require_role("clinician"))`` adds the authorisation layer on top of it.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthConfigurationError, AuthError, verify_token
from app.db.session import get_db
from app.models.profile import Profile, UserRole


class CurrentUser(BaseModel):
    """Who is calling: the auth user id, their role, and the raw access token."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    role: UserRole
    display_name: str | None
    token: str


class AuthIdentity(BaseModel):
    """A verified token holder with no profile yet — enough to bootstrap one, nothing more.

    Only routes that create or repair the caller's own ``profiles`` row may use it; anything
    that reads application data must go through :class:`CurrentUser` so the role is consulted.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    token: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(request: Request) -> str:
    scheme, _, credentials = request.headers.get("Authorization", "").partition(" ")
    token = credentials.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("missing bearer token")
    return token


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser:
    """Authenticate the caller from the ``Authorization: Bearer`` header.

    Raises 401 when the header is absent or the token is invalid, expired, or belongs to
    a user with no usable profile; 500 when this server cannot verify tokens at all.
    """
    token = _bearer_token(request)

    try:
        claims = await verify_token(token)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="authentication is not configured on this server",
        ) from exc
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized("token subject is not a user id") from exc

    profile = await session.get(Profile, user_id)
    if profile is None:
        raise _unauthorized("no profile for this user")
    if profile.role is None:
        raise _unauthorized("profile has no role assigned")

    return CurrentUser(
        id=user_id,
        role=profile.role,
        display_name=profile.display_name,
        token=token,
    )


CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


async def get_auth_identity(request: Request) -> AuthIdentity:
    """Verify the bearer token without requiring a profile row.

    This is the onboarding door: it proves who the caller is so ``POST /api/profiles/me``
    can create exactly that caller's own patient profile. It deliberately grants nothing
    else — no application data is readable without a profile-backed ``CurrentUser``.
    """
    token = _bearer_token(request)

    try:
        claims = await verify_token(token)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="authentication is not configured on this server",
        ) from exc
    except AuthError as exc:
        raise _unauthorized(str(exc)) from exc

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized("token subject is not a user id") from exc

    return AuthIdentity(id=user_id, token=token)


AuthIdentityDependency = Annotated[AuthIdentity, Depends(get_auth_identity)]


def require_role(*roles: UserRole | str) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """Build a dependency that accepts only callers holding one of ``roles`` (else 403)."""
    allowed = frozenset(UserRole(role) for role in roles)
    if not allowed:
        raise ValueError("require_role needs at least one role")

    required = " or ".join(sorted(role.value for role in allowed))

    async def dependency(user: CurrentUserDependency) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role: {required}",
            )
        return user

    return dependency
