"""Auth and roles: JWT verification, profile-backed roles, and the 401 / 403 split.

Covers the contract the rest of the API consumes: ``Depends(get_current_user)`` for any
authenticated caller, ``Depends(require_role("clinician"))`` for a specific role.
"""

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import jwt
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.core.config import Settings
from app.core.deps import CurrentUser, CurrentUserDependency, require_role
from app.main import app as real_app
from app.models.profile import UserRole


def guarded_app() -> FastAPI:
    """A minimal app whose only protection is the dependencies under test."""
    app = FastAPI()

    @app.get("/me")
    async def me(user: CurrentUserDependency) -> dict[str, str | None]:
        return {"id": str(user.id), "role": user.role.value, "display_name": user.display_name}

    @app.get("/me/token")
    async def me_token(user: CurrentUserDependency) -> dict[str, str]:
        return {"token": user.token}

    @app.get("/clinician-only")
    async def clinician_only(
        user: Annotated[CurrentUser, Depends(require_role("clinician"))],
    ) -> dict[str, str]:
        return {"id": str(user.id)}

    @app.get("/patient-only")
    async def patient_only(
        user: Annotated[CurrentUser, Depends(require_role(UserRole.PATIENT))],
    ) -> dict[str, str]:
        return {"id": str(user.id)}

    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=guarded_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as new_client:
        yield new_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- the five required cases -------------------------------------------------------------


async def test_valid_patient_authenticates(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT, display_name="Pat")

    response = await client.get("/me", headers=bearer(make_token(user_id)))

    assert response.status_code == 200
    assert response.json() == {"id": str(user_id), "role": "patient", "display_name": "Pat"}


async def test_valid_clinician_passes_the_clinician_guard(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.CLINICIAN, display_name="Dr")

    response = await client.get("/clinician-only", headers=bearer(make_token(user_id)))

    assert response.status_code == 200
    assert response.json() == {"id": str(user_id)}


async def test_expired_token_is_401(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)
    token = make_token(user_id, lifetime=-timedelta(hours=1))

    response = await client.get("/me", headers=bearer(token))

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


async def test_tampered_token_is_401(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    """Any edit to a verified token breaks the signature, including a changed subject."""
    user_id = await seed_profile(role=UserRole.PATIENT)
    attacker_id = UUID(int=0xDEADBEEF)
    token = make_token(user_id)
    claims = jwt.decode(token, options={"verify_signature": False})
    tampered = jwt.encode(
        claims | {"sub": str(attacker_id), "role": "clinician"},
        "an-independent-hs256-key-that-is-not-the-configured-one",
        algorithm="HS256",
    )

    response = await client.get("/me", headers=bearer(tampered))

    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


async def test_wrong_role_is_403(client: AsyncClient, make_token: Any, seed_profile: Any) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)

    response = await client.get("/clinician-only", headers=bearer(make_token(user_id)))

    assert response.status_code == 403
    assert response.json()["detail"] == "requires role: clinician"


# --- token handling ----------------------------------------------------------------------


async def test_missing_header_is_401(client: AsyncClient) -> None:
    response = await client.get("/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Basic dXNlcjpwYXNz", "Bearer    "],
    ids=["empty", "no-credentials", "wrong-scheme", "whitespace-only"],
)
async def test_unusable_authorization_header_is_401(client: AsyncClient, header: str) -> None:
    response = await client.get("/me", headers={"Authorization": header})

    assert response.status_code == 401


async def test_scheme_and_case_are_tolerated(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)
    token = make_token(user_id)

    response = await client.get("/me", headers={"Authorization": f"BEARER  {token} "})

    assert response.status_code == 200


async def test_garbage_token_is_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer("not-a-jwt"))

    assert response.status_code == 401


async def test_foreign_signing_key_is_401(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)
    token = make_token(user_id, secret="a-completely-different-hs256-signing-key-value")

    response = await client.get("/me", headers=bearer(token))

    assert response.status_code == 401


async def test_alg_none_is_401(client: AsyncClient, seed_profile: Any) -> None:
    """The accepted algorithms come from configuration, never from the token's own header."""
    user_id = await seed_profile(role=UserRole.PATIENT)
    now = int(datetime.now(UTC).timestamp())

    def segment(part: Any) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

    header = segment({"alg": "none", "typ": "JWT"})
    payload = segment({"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600})

    response = await client.get("/me", headers=bearer(f"{header}.{payload}."))

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"audience": None}, 'missing the "aud" claim'),
        ({"audience": "anonymous"}, "Audience doesn't match"),
        ({"lifetime": None}, 'missing the "exp" claim'),
    ],
    ids=["no-audience", "wrong-audience", "no-expiry"],
)
async def test_claim_requirements_are_enforced(
    client: AsyncClient, make_token: Any, seed_profile: Any, kwargs: dict, reason: str
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)

    response = await client.get("/me", headers=bearer(make_token(user_id, **kwargs)))

    assert response.status_code == 401
    assert reason in response.json()["detail"]


async def test_subject_must_be_a_user_id(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    response = await client.get("/me", headers=bearer(make_token("service_role")))

    assert response.status_code == 401
    assert response.json()["detail"] == "token subject is not a user id"


# --- the profile decides the role --------------------------------------------------------


async def test_token_without_profile_row_is_401(client: AsyncClient, make_token: Any) -> None:
    response = await client.get("/me", headers=bearer(make_token(UUID(int=42))))

    assert response.status_code == 401
    assert response.json()["detail"] == "no profile for this user"


async def test_profile_with_no_role_is_401(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=None, display_name="Unassigned")

    response = await client.get("/me", headers=bearer(make_token(user_id)))

    assert response.status_code == 401
    assert response.json()["detail"] == "profile has no role assigned"


async def test_role_claim_in_the_token_is_ignored(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    """A patient cannot self-declare as clinician in their token; profiles is the source."""
    user_id = await seed_profile(role=UserRole.PATIENT)

    response = await client.get(
        "/clinician-only", headers=bearer(make_token(user_id, role="clinician"))
    )

    assert response.status_code == 403


async def test_clinician_is_rejected_by_patient_guard(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.CLINICIAN)

    response = await client.get("/patient-only", headers=bearer(make_token(user_id)))

    assert response.status_code == 403


def test_require_role_needs_at_least_one_role() -> None:
    with pytest.raises(ValueError, match="at least one role"):
        require_role()


# --- server-side configuration -----------------------------------------------------------


async def test_current_user_carries_the_raw_token(
    client: AsyncClient, make_token: Any, seed_profile: Any
) -> None:
    user_id = await seed_profile(role=UserRole.PATIENT)
    token = make_token(user_id)

    response = await client.get("/me/token", headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {"token": token}


async def test_unconfigured_verification_key_is_500(
    client: AsyncClient,
    make_token: Any,
    seed_profile: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing keys are our fault, not the caller's: never a silent 401."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(supabase_jwt_secret="", supabase_jwks_uri=""),
    )
    user_id = await seed_profile(role=UserRole.PATIENT)

    response = await client.get("/me", headers=bearer(make_token(user_id)))

    assert response.status_code == 500
    assert response.json()["detail"] == "authentication is not configured on this server"


async def test_the_shipped_app_protects_auth_me() -> None:
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as real_client:
        response = await real_client.get("/auth/me")

    assert response.status_code == 401
