"""Key-source resolution: JWKS wins over the stale legacy secret, and algorithms follow keys.

The exact failure these prevent: Supabase keeps ``SUPABASE_JWT_SECRET`` populated after a
project starts signing tokens with an ES256 signing key. If the secret were consulted first,
every real login would be rejected as "alg not allowed" — which happened in the field.

``Settings`` reads the ambient environment (the developer's real .env counts too), so every
test passes all three key-source fields explicitly instead of relying on defaults.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWK

from app.core import security
from app.core.config import Settings
from app.core.security import AuthError, verify_token

TEST_KID = "test-es256-kid"


def settings_for(*, jwks: str = "", secret: str = "") -> Settings:
    return Settings(
        supabase_jwks_uri=jwks,
        supabase_jwt_secret=secret,
        supabase_issuer="",
        supabase_jwt_audience="authenticated",
    )


def es256_key_pair() -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.public_key().public_numbers()
    coord = lambda n: n.to_bytes(32, "big")  # noqa: E731
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "use": "sig",
        "kid": TEST_KID,
        "x": _b64u(coord(numbers.x)),
        "y": _b64u(coord(numbers.y)),
    }
    return private, jwk


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def es256_token(private: ec.EllipticCurvePrivateKey, *, header_kid: str = TEST_KID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(uuid4()), "iat": now, "exp": now + timedelta(hours=1), "aud": "authenticated"},
        private,
        algorithm="ES256",
        headers={"kid": header_kid},
    )


@pytest.fixture
def stub_jwks(monkeypatch: pytest.MonkeyPatch):
    """Serve a fixed JWKS document without touching the network."""

    def install(keys: list[dict[str, Any]]) -> None:
        async def fake_fetch(uri: str) -> dict[str, tuple[PyJWK, list[str]]]:
            out: dict[str, tuple[PyJWK, list[str]]] = {}
            for entry in keys:
                algorithms = security._KTY_ALGORITHMS[entry["kty"]]
                out[entry["kid"]] = (PyJWK(entry, algorithm=algorithms[0]), algorithms)
            return out

        monkeypatch.setattr(security, "_fetch_jwks", fake_fetch)
        security._JWKS.__init__()  # drop any cached document

    yield install


async def test_es256_jwks_token_is_accepted(monkeypatch, stub_jwks):
    private, jwk = es256_key_pair()
    stub_jwks([jwk])
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(supabase_jwks_uri="https://example.invalid/jwks.json", supabase_jwt_secret=""),
    )

    claims = await verify_token(es256_token(private))
    assert "sub" in claims


async def test_stale_hs256_secret_does_not_shadow_the_jwks_key(monkeypatch, stub_jwks):
    """Both configured (the real-world state) and an ES256 token: verification must win."""
    private, jwk = es256_key_pair()
    stub_jwks([jwk])
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(
            supabase_jwks_uri="https://example.invalid/jwks.json",
            supabase_jwt_secret="legacy-secret-still-set-by-the-project",
            supabase_jwt_audience="authenticated",
        ),
    )

    claims = await verify_token(es256_token(private))
    assert "sub" in claims


async def test_public_key_cannot_forge_via_hmac(monkeypatch, stub_jwks):
    """The downgrade attack the docstring forbids: HS256-signed-with-the-public-key."""
    private, jwk = es256_key_pair()
    stub_jwks([jwk])
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(supabase_jwks_uri="https://example.invalid/jwks.json", supabase_jwt_secret=""),
    )

    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    attack = jwt.encode(
        {"sub": "attacker", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1),
         "aud": "authenticated"},
        public_pem,
        algorithm="HS256",
        headers={"kid": TEST_KID},
    )

    with pytest.raises(AuthError):
        await verify_token(attack)


async def test_unknown_kid_is_refused(monkeypatch, stub_jwks):
    private, jwk = es256_key_pair()
    stub_jwks([jwk])
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(supabase_jwks_uri="https://example.invalid/jwks.json", supabase_jwt_secret=""),
    )

    with pytest.raises(AuthError):
        await verify_token(es256_token(private, header_kid="someone-elses-key"))
