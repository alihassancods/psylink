from collections.abc import AsyncIterator

import pytest
from sqlalchemy import String, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.session import SessionLocal, engine


class SampleRow(Base):
    """Test-only table; created and dropped around the ORM tests below."""

    __tablename__ = "pytest_sample_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as new_session:
        await new_session.rollback()
        yield new_session
        await new_session.rollback()


@pytest.fixture
async def table_session() -> AsyncIterator[AsyncSession]:
    """Session over a freshly created table.

    The session is closed *before* the table is dropped: DROP TABLE needs an
    ACCESS EXCLUSIVE lock, which a still-open session would block forever.
    """
    table = SampleRow.__table__
    async with engine.begin() as conn:
        await conn.run_sync(table.drop, checkfirst=True)
        await conn.run_sync(table.create)

    async with SessionLocal() as new_session:
        yield new_session
        await new_session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(table.drop, checkfirst=True)


async def test_driver_is_real_postgres(session: AsyncSession) -> None:
    raw = (await session.execute(text("SELECT version()"))).scalar_one()

    assert raw.startswith("PostgreSQL")


async def test_migrations_have_been_applied(session: AsyncSession) -> None:
    found = (
        await session.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'alembic_version' AND table_schema = 'public'"
            )
        )
    ).scalar_one_or_none()

    assert found == 1, "run `uv run alembic upgrade head` first"


async def test_orm_roundtrip(table_session: AsyncSession) -> None:
    table_session.add_all([SampleRow(name="alpha"), SampleRow(name="beta")])
    await table_session.commit()

    stored = (await table_session.scalars(select(SampleRow.name).order_by(SampleRow.name))).all()

    assert stored == ["alpha", "beta"]


async def test_primary_key_is_generated(table_session: AsyncSession) -> None:
    row = SampleRow(name="one")
    table_session.add(row)
    await table_session.commit()

    assert row.id is not None


async def test_rollback_discards_uncommitted_writes(table_session: AsyncSession) -> None:
    with pytest.raises(RuntimeError):
        async with table_session.begin():
            table_session.add(SampleRow(name="doomed"))
            await table_session.flush()
            raise RuntimeError("abort the transaction")

    async with SessionLocal() as checker:
        names = (await checker.scalars(select(SampleRow.name))).all()

    assert "doomed" not in names
