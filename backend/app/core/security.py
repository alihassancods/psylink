"""Verification of Supabase-issued JWTs.

Hosted Supabase projects sign access tokens with RS256 or, on newer projects, ES256, and
publish the matching public keys at ``<project>/auth/v1/.well-known/jwks.json``; self-hosted
or legacy GoTrue uses HS256 with a shared secret. Which key source applies is decided by
configuration, never by the token's own ``alg`` header, so a client cannot downgrade RS256
verification into HMAC-signed-with-the-public-key. The accepted algorithms come from the
key's own type (RSA→RS256, EC→ES256), never from the token either.

A project can outlive its HS256 secret: Supabase keeps ``SUPABASE_JWT_SECRET`` populated even
after a project moves to JWKS-signed tokens, and a stale secret would then reject every real
login. So when a JWKS URI is configured it wins, and the shared secret is the fallback for
deployments that deliberately left the URI out.
"""

import asyncio
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK
from jwt.exceptions import InvalidKeyError, PyJWTError

from app.core.config import Settings, get_settings

LEEWAY_SECONDS = 30.0
JWKS_TTL_SECONDS = 3600.0
JWKS_TIMEOUT_SECONDS = 5.0

REQUIRED_CLAIMS = ["exp", "sub", "aud"]


class AuthError(Exception):
    """The token was presented but cannot be accepted; the caller can fix it (401)."""


class AuthConfigurationError(Exception):
    """This server cannot verify tokens at all; an operator problem, never the caller's (500)."""


async def verify_token(token: str) -> dict[str, Any]:
    """Return the verified claims of a Supabase access token.

    Signature, expiry and audience are always checked; the issuer only when configured.
    Raises AuthConfigurationError when no verification key is available and AuthError for
    an expired token, a bad signature, or a missing required claim.
    """
    settings = get_settings()
    key, algorithms = await _resolve_key(token, settings)

    options: dict[str, Any] = {"require": REQUIRED_CLAIMS}
    if settings.supabase_issuer:
        options["verify_iss"] = True

    try:
        return jwt.decode(
            token,
            key=key,
            algorithms=algorithms,
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_issuer or None,
            leeway=LEEWAY_SECONDS,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token has expired") from exc
    except PyJWTError as exc:
        raise AuthError(f"token is not valid: {exc}") from exc


async def _resolve_key(token: str, settings: Settings) -> tuple[Any, list[str]]:
    if settings.supabase_jwks_uri:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except PyJWTError as exc:
            raise AuthError("token is not a well-formed JWT") from exc
        entry = await _JWKS.key_for(kid, settings.supabase_jwks_uri)
        if entry is None:
            raise AuthError("no verification key matches this token")
        return entry

    if settings.supabase_jwt_secret:
        return settings.supabase_jwt_secret, ["HS256"]

    raise AuthConfigurationError(
        "no Supabase verification key configured: set SUPABASE_JWKS_URI or SUPABASE_JWT_SECRET"
    )


class _JwksCache:
    """Caches the JWKS document so requests don't each hit the network.

    A token whose ``kid`` is unknown forces exactly one refetch, which is how key
    rotation is picked up without waiting for the TTL.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._keys: dict[str, tuple[PyJWK, list[str]]] = {}
        self._uri: str = ""
        self._fetched_at: float = 0.0

    async def key_for(
        self, kid: str | None, uri: str
    ) -> tuple[PyJWK, list[str]] | None:
        for force_refresh in (False, True):
            async with self._lock:
                if force_refresh or self._uri != uri or self._is_stale():
                    self._keys = await _fetch_jwks(uri)
                    self._uri = uri
                    self._fetched_at = time.monotonic()

            if kid is None:
                if len(self._keys) != 1:
                    return None
                return next(iter(self._keys.values()))

            entry = self._keys.get(kid)
            if entry is not None:
                return entry

        return None

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) > JWKS_TTL_SECONDS


#: The one signature algorithm each published key type is allowed to verify with. Chosen by
#: the key, never by the token header, so a header cannot steer verification.
_KTY_ALGORITHMS = {"RSA": ["RS256"], "EC": ["ES256"]}


async def _fetch_jwks(uri: str) -> dict[str, tuple[PyJWK, list[str]]]:
    try:
        async with httpx.AsyncClient(timeout=JWKS_TIMEOUT_SECONDS) as client:
            response = await client.get(uri)
            response.raise_for_status()
            document = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthConfigurationError(f"cannot load the JWKS document from {uri}: {exc}") from exc

    if not isinstance(document, dict):
        raise AuthConfigurationError(f"JWKS document at {uri} is not an object")

    keys: dict[str, tuple[PyJWK, list[str]]] = {}
    for index, entry in enumerate(document.get("keys", [])):
        if not isinstance(entry, dict) or entry.get("use", "sig") != "sig":
            continue
        algorithms = _KTY_ALGORITHMS.get(entry.get("kty", ""))
        if algorithms is None:
            continue
        try:
            jwk = PyJWK(entry, algorithm=algorithms[0])
        except InvalidKeyError, PyJWTError:
            continue
        keys[entry.get("kid") or f"anon-{index}"] = (jwk, algorithms)

    return keys


_JWKS = _JwksCache()
