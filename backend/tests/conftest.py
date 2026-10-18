import os
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

# app.db.session builds its engine from Settings at import time, so the test database URL
# has to be in the environment before anything under ``app`` is imported. The suite always
# targets the docker-compose Postgres, regardless of where the developer's .env points.
# Override the target with TEST_DATABASE_URL.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://backend:backend@127.0.0.1:5433/backend",
)

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import security
from app.core.config import Settings
from app.db.session import SessionLocal, engine
from app.models.profile import Profile, UserRole

JWT_SECRET = "test-only-hs256-secret-never-used-outside-the-suite"


@pytest.fixture(autouse=True)
async def dispose_engine() -> AsyncIterator[None]:
    """Each test gets its own event loop, so the asyncpg pool must not outlive it."""
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def locally_signed_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify against a local HS256 key instead of a real Supabase project."""
    settings = Settings(
        supabase_jwt_secret=JWT_SECRET,
        supabase_jwks_uri="",
        supabase_jwt_audience="authenticated",
        supabase_issuer="",
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)


MakeToken = Callable[..., str]
SeedProfile = Callable[..., Awaitable[UUID]]


@pytest.fixture
def make_token() -> MakeToken:
    """Mint a Supabase-shaped access token: sub/iat/exp/aud, plus anything else wanted."""

    def factory(
        user_id: UUID | str,
        *,
        lifetime: timedelta | None = timedelta(hours=1),
        secret: str = JWT_SECRET,
        audience: str | None = "authenticated",
        **extra: Any,
    ) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {"sub": str(user_id), "iat": now}
        if lifetime is not None:
            claims["exp"] = now + lifetime
        if audience is not None:
            claims["aud"] = audience
        claims.update(extra)
        return jwt.encode(claims, secret, algorithm="HS256")

    return factory


@pytest.fixture
async def seed_profile() -> AsyncIterator[SeedProfile]:
    """Insert a real profiles row and remove it afterwards. Returns the new user id."""
    created: list[UUID] = []

    async def factory(
        *,
        role: UserRole | None = UserRole.PATIENT,
        display_name: str | None = "Test Person",
    ) -> UUID:
        user_id = uuid4()
        async with SessionLocal() as session:
            session.add(Profile(id=user_id, role=role, display_name=display_name))
            await session.commit()
        created.append(user_id)
        return user_id

    yield factory

    async with SessionLocal() as session:
        await session.execute(delete(Profile).where(Profile.id.in_(created)))
        await session.commit()


SeedConsent = Callable[..., Awaitable[UUID]]


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """An HTTP client over the real application, so router wiring is part of the test."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def seed_consent() -> AsyncIterator[SeedConsent]:
    """Grant one profile access to another's data, committed for other transactions to see.

    Teardown is not needed: consents cascade from `profiles`, and `seed_profile` removes the
    profiles it created.
    """

    async def factory(patient_id: UUID | str, clinician_id: UUID | str) -> UUID:
        from app.services.db import service_client

        async with service_client() as db:
            row = await db.insert(
                "consents",
                {"patient_id": str(patient_id), "clinician_id": str(clinician_id)},
                returning=("id",),
            )
        assert row is not None
        return row["id"]

    yield factory


@pytest.fixture
def rows_for() -> Callable[..., Awaitable[list[dict[str, Any]]]]:
    """Read rows as the service identity — assertions about what actually got stored."""

    async def fetch(table: str, /, *, where: str, **params: Any) -> list[dict[str, Any]]:
        from app.services.db import service_client

        async with service_client() as db:
            return await db.fetch(f"select * from public.{table} where {where}", **params)

    return fetch
