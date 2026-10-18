"""1.1 foundation: CORS on the configured origins, and the 500 error shape.

The 500 body is a safety surface as much as a UX one: an unhandled exception is the one path
where library error text (which embeds bound parameters, i.e. patient words) could reach the
browser, so it must be replaced by a code and a generic line.
"""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, cors_origins
from app.main import app


def test_cors_origins_parsing() -> None:
    assert cors_origins(Settings(_env_file=None, frontend_origin="http://a, https://b ")) == [
        "http://a",
        "https://b",
    ]
    assert cors_origins(Settings(_env_file=None, frontend_origin="")) == []
    assert cors_origins(Settings(_env_file=None, frontend_origin="http://x,,http://y")) == [
        "http://x",
        "http://y",
    ]


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def test_preflight_is_allowed_for_a_configured_origin(client) -> None:
    response = await client.options(
        "/api/checkins",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_an_unknown_origin_gets_no_cors_header(client) -> None:
    response = await client.get("/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_unhandled_exception_becomes_the_standard_shape(caplog) -> None:
    """A crash inside a route must not leak the exception text to the browser or the log.

    `raise_app_exceptions=False` because the handler under test is the *server's* last line of
    defence: by default the test transport re-raises instead of returning the response the way
    uvicorn would.
    """

    async def boom() -> dict[str, str]:
        raise RuntimeError("insert into checkins ... [parameters: (PATIENT-WORDS,)]")

    app.add_api_route("/_boom", boom, methods=["GET"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as raw_client:
            with caplog.at_level(logging.ERROR, logger="app.main"):
                response = await raw_client.get("/_boom")
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/_boom"]

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "internal_error"
    assert isinstance(detail["message"], str) and detail["message"]
    assert "PATIENT-WORDS" not in response.text
    assert "PATIENT-WORDS" not in caplog.text
    assert "RuntimeError" in caplog.text  # the operator still gets a usable class name
