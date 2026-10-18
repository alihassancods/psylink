import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import checkins, consent, transcribe
from app.core.config import cors_origins, get_settings
from app.core.deps import CurrentUser, get_current_user
from app.db.session import engine, get_db

logger = logging.getLogger(__name__)

#: Codes the frontend may switch on. Everything else must land on the fallback branch.
INTERNAL_ERROR_CODE = "internal_error"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# The browser calls this API from a different origin than the one it was served from, so the
# preflight has to succeed. Only the origins in FRONTEND_ORIGIN are allowed, and credentials
# are off because auth travels in the Authorization header, not a cookie.
_origins = cors_origins(settings)
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """The standard error shape for anything that escaped a route.

    A 500 must not decide what the patient sees: the body carries a code and a generic line,
    never the exception text — which is exactly where a patient's words could be echoed back,
    since SQLAlchemy writes bound parameters into its error messages. The log records the
    class name for the operator and nothing more.
    """
    logger.error(
        "unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": INTERNAL_ERROR_CODE,
                "message": "Something went wrong. Please type instead.",
            }
        },
    )


app.include_router(consent.router)
app.include_router(checkins.router)
app.include_router(transcribe.router)


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
