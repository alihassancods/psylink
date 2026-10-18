from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user
from app.db.session import engine, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
async def health_db(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/auth/me")
async def auth_me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str | None]:
    return {"id": str(user.id), "role": user.role.value, "display_name": user.display_name}
