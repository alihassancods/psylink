from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Supabase's transaction-mode pooler (port 6543) hands each statement to whichever server
# connection is free, so an asyncpg prepared statement cached on one is missing on the next
# ("prepared statement already exists"). Turning its cache off makes the same URL work through
# the transaction pooler, the session pooler, and a direct connection alike.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
