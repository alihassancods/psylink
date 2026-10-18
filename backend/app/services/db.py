"""Database access where Postgres, not application code, decides who may see a row.

Two ways in, one rule:

``user_client(token)``
    Verifies a Supabase access token, then assumes the ``authenticated`` database role for a
    single transaction and publishes the verified claims as ``request.jwt.claims`` — the same
    setting PostgREST writes. Every policy in ``supabase/migrations/002_rls.sql`` therefore
    applies to whatever the request does, including reads no handler checked.

``service_client()``
    Stays as the connection owner, which Postgres exempts from row-level security. Only for
    system writes: raising alerts and seeding demo data. Never hand it a caller's input.

``has_active_consent(patient_id)``
    The Python side of ``app.has_active_consent()``, so application code and the policies cannot
    drift apart on who is allowed to see whom.

Values for ``uuid`` columns are passed as :class:`uuid.UUID`; a ``jsonb`` column takes a dict, or
any other JSON document wrapped in :class:`Json`.
"""

import json
import re
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.security import AuthError, verify_token
from app.db.session import engine

#: The non-privileged role a person's request runs as. Supabase names it `authenticated`.
AUTHENTICATED_ROLE = "authenticated"

#: GUC the policies read. PostgREST sets this on Supabase; we set the same one here.
CLAIMS_SETTING = "request.jwt.claims"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")

Row = Mapping[str, Any]


class Json:
    """Mark a value as a JSON document for a `jsonb` column.

    A plain dict already goes over as jsonb, so this is only needed for documents that are not
    objects — `Json([1, 2, 3])` — because a bare list is otherwise a Postgres array.
    """

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


def _identifier(name: str) -> str:
    """Validate a table or column name, since those are the parts a query cannot parameterise."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def _bind_value(value: Any) -> Any:
    """JSON documents travel as text so asyncpg hands Postgres a valid jsonb literal.

    Values inside them that JSON has no type for — a UUID or a datetime — go as their string
    form, which is what a document would store anyway. Lists that are not wrapped stay arrays.
    """
    if isinstance(value, Json):
        return json.dumps(value.value, default=str)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return value


def _bind_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _bind_value(value) for key, value in params.items()}


def _columns(columns: Iterable[str]) -> str:
    return ", ".join("*" if column == "*" else _identifier(column) for column in columns) or "*"


def _as_row(row: Any) -> Row:
    """Column-name → value, which is how the rest of the stack (and PostgREST) hands rows over.

    A `Row` itself iterates its *values*, so `dict(row)` would read it positionally.
    """
    return dict(row._mapping)


class DbClient:
    """Query surface over one transaction, carrying whatever identity that transaction has.

    Obtained from :func:`user_client` or :func:`service_client` and only valid inside that
    context manager: the assumed role and the claims are transaction-local, so using the client
    afterwards would mean using it with no identity at all.
    """

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def fetch(self, statement: str, /, **params: Any) -> list[Row]:
        """Run a read and return every row as a mapping."""
        return [_as_row(row) for row in await self._rows(statement, params)]

    async def fetchrow(self, statement: str, /, **params: Any) -> Row | None:
        """Run a read and return the first row, or None when there is none."""
        rows = await self._rows(statement, params)
        return _as_row(rows[0]) if rows else None

    async def scalar(self, statement: str, /, **params: Any) -> Any:
        """Run a read and return the first column of the first row."""
        row = await self.fetchrow(statement, **params)
        return next(iter(row.values())) if row else None

    async def execute(self, statement: str, /, **params: Any) -> int:
        """Run a write and return how many rows it touched."""
        result = await self._connection.execute(text(statement), _bind_params(params))
        return result.rowcount

    async def select(
        self,
        table: str,
        /,
        *,
        columns: Iterable[str] = ("*",),
        where: str | None = None,
        params: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[Row]:
        """Read rows of ``table``; the caller's identity decides which ones exist for them."""
        sql = f"select {_columns(columns)} from {_identifier(table)}"
        if where:
            sql += f" where {where}"
        if order_by:
            sql += f" order by {order_by}"
        if limit is not None:
            sql += f" limit {int(limit)}"

        return await self.fetch(sql, **(params or {}))

    async def insert(
        self,
        table: str,
        /,
        values: Mapping[str, Any],
        *,
        returning: Sequence[str] = ("*",),
    ) -> Row | None:
        """Add one row and get it back, defaults and generated ids included.

        Row-level security still gets the final say: a row the caller is not allowed to write
        raises rather than quietly disappearing.
        """
        columns = ", ".join(_identifier(name) for name in values)
        placeholders = ", ".join(f":{name}" for name in values)
        sql = (
            f"insert into {_identifier(table)} ({columns}) "
            f"values ({placeholders}) returning {_columns(returning)}"
        )
        rows = await self._rows(sql, values)
        return _as_row(rows[0]) if rows else None

    async def update(
        self,
        table: str,
        /,
        values: Mapping[str, Any],
        *,
        where: str,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """Change matching rows and return the count. A row RLS hides is simply not changed."""
        assignments = ", ".join(f"{_identifier(name)} = :set_{name}" for name in values)
        bound: dict[str, Any] = {f"set_{name}": value for name, value in values.items()}
        bound.update(params or {})
        sql = f"update {_identifier(table)} set {assignments} where {where}"

        return await self.execute(sql, **bound)

    async def _rows(self, statement: str, params: Mapping[str, Any] | None) -> Sequence[Any]:
        result = await self._connection.execute(text(statement), _bind_params(params or {}))
        return result.fetchall()


@asynccontextmanager
async def user_client(token: str) -> AsyncIterator[DbClient]:
    """Open a request-scoped client whose every query is filtered by row-level security.

    Raises ``AuthError`` (map it to 401) for a token that is not signed, is expired, or has no
    usable ``sub``, and ``AuthConfigurationError`` (500) when this server cannot verify tokens.
    """
    claims = await verify_token(token)

    try:
        user_id = UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise AuthError("token subject is not a user id") from exc

    # PostgREST always publishes a role claim, so mirror it: policies written against a real
    # Supabase project behave the same here. The verified subject wins over any `role` claim.
    payload = {"role": AUTHENTICATED_ROLE, **claims, "sub": str(user_id)}

    async with engine.begin() as connection:
        await _assume_role(connection, payload)
        yield DbClient(connection)


@asynccontextmanager
async def service_client() -> AsyncIterator[DbClient]:
    """Open a client that bypasses row-level security, for system writes only.

    The connection owner is exempt from RLS, so this sees every row of every table. Reserve it
    for raising alerts and seeding demo data; anything serving a person's request goes through
    :func:`user_client` instead.
    """
    async with engine.begin() as connection:
        yield DbClient(connection)


async def _assume_role(connection: AsyncConnection, claims: Mapping[str, Any]) -> None:
    """Enter the caller's identity for the rest of this transaction.

    Both the role and the claims are transaction-scoped, so the pooled connection returns clean
    and a transaction-pooling proxy cannot carry one request's identity into the next.
    """
    await connection.execute(text(f"set local role {_identifier(AUTHENTICATED_ROLE)}"))
    await connection.execute(
        text("select set_config(:setting, :claims, true)"),
        {"setting": CLAIMS_SETTING, "claims": json.dumps(claims)},
    )


async def has_active_consent(
    patient_id: UUID | str,
    /,
    *,
    clinician_id: UUID | str | None = None,
    client: DbClient | None = None,
    token: str | None = None,
) -> bool:
    """Is there an unrevoked consent linking a clinician to this patient?

    Three ways to say who the clinician is, for the three places the question comes up:

    ``client``
        Ask inside an existing transaction — normally the caller's own ``user_client``, where
        leaving ``clinician_id`` out means "the person holding this client".
    ``token``
        Open a request-scoped client for that bearer and ask the same question.
    ``clinician_id``
        Ask for an explicit pair over the service connection, for pipeline jobs with no request
        in hand.

    Anything else raises ``ValueError`` rather than defaulting to a vantage point that sees
    everything, because a silent bypass here would undo what the policies enforce.
    """
    statement = "select app.has_active_consent(:patient_id, :clinician_id)"
    params = {"patient_id": patient_id, "clinician_id": clinician_id}

    if client is not None:
        return bool(await client.scalar(statement, **params))

    if token is not None:
        async with user_client(token) as scoped:
            return bool(await scoped.scalar(statement, **params))

    if clinician_id is not None:
        async with service_client() as scoped:
            return bool(await scoped.scalar(statement, **params))

    raise ValueError("has_active_consent needs one of client=, token=, or clinician_id=")


__all__ = ["DbClient", "Json", "has_active_consent", "service_client", "user_client"]
