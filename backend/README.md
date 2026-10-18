# backend

FastAPI + PostgreSQL backend, managed with [uv](https://docs.astral.sh/uv/).

## Stack

| Purpose | Package |
| --- | --- |
| Web framework | `fastapi[standard]` |
| ASGI server | `uvicorn[standard]` |
| ORM | `sqlalchemy[asyncio]` 2.x |
| PostgreSQL driver | `asyncpg` |
| Settings / env parsing | `pydantic-settings` |
| JWT verification | `pyjwt[crypto]` |
| Migrations | `alembic` |

Dev: `ruff` (lint + format), `pytest`, `pytest-asyncio`, `httpx`.
Python 3.14, virtualenv in `.venv/` (created and managed by uv — no `pip`/`venv` needed).

## Setup

```bash
cd backend
uv sync                  # install/lock dependencies
cp .env.example .env     # then edit DATABASE_URL as needed
```

## Run PostgreSQL

```bash
docker compose up -d db
```

That serves `backend:backend@127.0.0.1:5433/backend`, matching `.env.example`. Port **5433** is
used because host port 5432 is already taken by an unrelated project's Postgres container; ours is
bound to loopback only. If you prefer a managed or system Postgres, point `DATABASE_URL` at it
instead.

URL format: `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME`

## Run the API

```bash
uv run fastapi dev app/main.py       # dev server with reload, http://localhost:8000
uv run uvicorn app.main:app          # production-style server
```

Endpoints: `GET /health` (app only), `GET /health/db` (runs `SELECT 1`), `GET /auth/me` (requires a bearer
token), docs at `/docs`.

## Authentication

Supabase issues the JWT; the backend only verifies it and then asks the database who that user is.

- `app/core/security.py` — `verify_token()` checks signature, expiry (30s leeway) and audience. The accepted
  algorithm comes from configuration, never from the token's own `alg` header: set `SUPABASE_JWKS_URI` for a
  hosted project (RS256, keys cached for an hour and refetched on an unknown `kid`) **or**
  `SUPABASE_JWT_SECRET` for self-hosted/legacy GoTrue (HS256). With neither set, requests fail as 500 — a
  server misconfiguration is not the caller's to fix.
- `app/core/deps.py` — `get_current_user` reads `Authorization: Bearer <token>`, loads the `profiles` row, and
  returns `CurrentUser(id, role, display_name, token)`. The role always comes from `profiles`; a `role` claim
  inside the token is ignored.
- `require_role("clinician")` guards a route on top of that.

Status codes: **401** for a missing/malformed/expired/tampered token, a wrong audience, a subject that isn't a
UUID, or a user with no profile row (or no role yet). **403** for an authenticated caller holding the wrong
role.

```bash
uv run fastapi dev app/main.py
curl -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" http://localhost:8000/auth/me
```

## Schema & row-level security

`supabase/migrations/001_schema.sql` and `002_rls.sql` are the canonical schema. The access rules
live in Postgres, so a query that skips the handler someone intended still cannot reach another
patient's rows.

| Table | Written by | Read by |
| --- | --- | --- |
| `profiles` | the person (a self-insert is capped at `role = 'patient'`), service for clinician onboarding | self; a clinician also reads the patients they have an active consent for |
| `consents` | the patient (grant, revoke), service for demo seed | only the two parties named in the row |
| `checkins` | the patient | patient; clinician with an active consent |
| `analyses` | service only | patient; clinician with an active consent |
| `alerts` | service only | the patient it concerns; the addressed clinician, and only while the consent is active |

A consent is active while `revoked_at is null`. Revoking hides **history** as well as new rows: a
clinician whose access was withdrawn can no longer read the old check-ins, analyses, or alerts.
Nothing a person does can delete a consent row — withdrawal stamps `revoked_at` so the trail survives.

Roles are read from `profiles`, never from the token: `app.current_user_role()` queries the table, so
a `role` claim inside a JWT is decoration. A subject with no `profiles` row sees nothing anywhere.

### The access layer — `app/services/db.py`

- `user_client(token)` — verifies the Supabase JWT, then `SET LOCAL ROLE authenticated` and publishes
  the verified claims as `request.jwt.claims`, the same setting PostgREST writes. Both are
  transaction-scoped, so a pooled connection never carries one caller into the next request.
- `service_client()` — stays as the connection owner, which Postgres exempts from RLS. For system
  writes only: raising alerts, seeding demo data. Never point it at caller input.
- `has_active_consent(patient_id, *, client=|token=|clinician_id=)` — the Python side of
  `app.has_active_consent()`, the one function the policies are built from, so route code and the
  database cannot drift apart. With none of the three it raises: there is no safe default vantage
  point to fall back to.

```python
from app.services.db import has_active_consent, user_client

async with user_client(current_user.token) as db:
    recent = await db.select("checkins", order_by="created_at desc", limit=20)
    if await has_active_consent(patient_id, client=db):
        await db.insert("checkins", {"patient_id": patient_id, "answers": {"mood": 4}})
```

`uuid` columns take `uuid.UUID`; `jsonb` takes a dict, or any other document wrapped in `Json(...)`.
A rejected write aborts its transaction — that is Postgres, not this layer — so a request that is
refused should end there instead of issuing more statements.

## Migrations

The two SQL files are the source of truth, and both application paths run the same text:

```bash
uv run alembic upgrade head     # local: revision b7e4c9d1a2f3 executes the files in order
supabase db push                # a hosted project: standard supabase/migrations directory
```

Every statement is written to be re-runnable (`if not exists`, `create or replace`,
`drop policy if exists`), so pushing files that Alembic already applied changes nothing. The alembic
revision splits each file into statements because asyncpg prepares one command at a time; that is
`app/services/sql_script.py`, which understands dollar-quoted bodies, string literals, and comments.

Down the barrel: these tables are defined in SQL, not in `Base.metadata`, so
`alembic revision --autogenerate` will propose **dropping** them. Add the model to `app/models/`
first, or write the revision by hand.

### Connecting to Supabase

`DATABASE_URL` needs the asyncpg scheme — `postgresql+asyncpg://...`. The dashboard shows
`postgresql://`, which makes SQLAlchemy import psycopg instead and fail at engine creation.
`app/db/session.py` sets asyncpg's `statement_cache_size = 0`, which is what makes the
**transaction-mode** pooler (port 6543) usable: prepared statements are cached per server connection
and that pooler multiplexes connections. The session pooler (5432) and a direct connection work too.

Supabase already ships `anon`, `authenticated`, and `service_role`; `002_rls.sql` creates the first
two only if they are missing, and grants `authenticated` its privileges there. Its `postgres` user is
a member of `authenticated` and holds `bypassrls`, which is exactly the pairing `user_client` and
`service_client` assume. `anon` is granted nothing at all, so an unauthenticated request is refused
before RLS is even consulted.

## Lint & format (ruff)

```bash
uv run ruff check .            # lint
uv run ruff check . --fix      # autofix
uv run ruff format .           # format
```

Config lives in `pyproject.toml` (`[tool.ruff]`), line length 100, target py314, with rules
`E,W,F,I,B,UP,C4,SIM,RUF,ASYNC`. `alembic/versions/` is excluded — those files come from
Alembic's own template.

## Tests

The suite hits the **real** Postgres, so `docker compose up -d db` and
`uv run alembic upgrade head` must have been run first. `tests/conftest.py` pins the suite to the
docker-compose database (`postgresql+asyncpg://backend:backend@127.0.0.1:5433/backend`) whatever your `.env`
points at; set `TEST_DATABASE_URL` to send it elsewhere.

```bash
uv run pytest              # or: uv run pytest -v
```

- `tests/test_health_api.py` — `/health` and `/health/db` over ASGI transport
- `tests/test_database.py` — server version is genuinely PostgreSQL, `alembic_version` exists,
  ORM insert/select roundtrip, generated primary key, rollback discards uncommitted writes
- `tests/test_auth_roles.py` — the five auth cases (valid patient, valid clinician, expired, tampered, wrong
  role) plus header variants, audience/expiry requirements, `alg: none`, tokens with no profile or no role,
  and a `role` claim that must not be honoured. Tokens are signed locally with HS256 — no Supabase project
  is contacted.
- `tests/rls/` — the access rules, asserted through real database roles rather than mocks:
  - `test_patient_isolation.py` — patient A cannot read or write patient B's rows, cannot re-point one of
    their own rows at B, cannot forge an analysis or promote themselves to clinician, and a `role` claim in
    the token buys nothing.
  - `test_clinician_consent.py` — the lifecycle: unlinked clinician sees nothing (even for an alert
    addressed to them), linking opens check-ins/analyses/alerts, revoking closes the history too, and both
    re-grant paths restore access.
  - `test_db_contract.py` — `user_client` vs `service_client` visibility, an identity not outliving its
    transaction, refused tokens (bad signature, expired, wrong audience, non-UUID subject), the three
    `has_active_consent` forms and its refusal to guess, identifier validation.
  - `test_schema_invariants.py` — RLS on and not forced on every table, both required indexes with the
    specified columns, the policy helpers installed, no permissive policy, every policy bound to
    `authenticated`, `anon` holding no privilege, helpers failing closed with no request.

Tests share the dev database and clean up after themselves (`pytest_sample_rows` is created and
dropped per test; seeded `profiles` rows are deleted by their fixture, which cascades everything
under it).

## Layout

```
backend/
├── alembic/            # migration environment (async engine wired to Settings)
│   └── versions/       # b7e4c9d1a2f3 applies the supabase/migrations SQL files
├── alembic.ini
├── app/
│   ├── core/
│   │   ├── config.py   # Settings (pydantic-settings, reads .env)
│   │   ├── security.py # Supabase JWT verification (RS256 via JWKS, or HS256)
│   │   └── deps.py     # CurrentUser, get_current_user, require_role
│   ├── db/
│   │   ├── base.py     # DeclarativeBase — models inherit from Base
│   │   └── session.py  # async engine, session factory, get_db dependency
│   ├── models/
│   │   └── profile.py  # UserRole + Profile (profiles table, keyed by auth uid)
│   ├── services/
│   │   ├── db.py       # user_client / service_client / has_active_consent
│   │   └── sql_script.py # statement splitter for applying .sql migrations over asyncpg
│   └── main.py         # FastAPI app + health and /auth/me endpoints
├── supabase/migrations/  # canonical schema: 001_schema.sql, 002_rls.sql
├── tests/              # pytest suite against the real database
│   └── rls/            # row-level security: isolation, consent lifecycle, contract, invariants
├── docker-compose.yml  # postgres:16-alpine
├── .env.example
└── pyproject.toml
```

To add a model, create `app/models/<name>.py` with classes inheriting `Base`, and import it
(e.g. from `alembic/env.py`) so `Base.metadata` sees it before autogenerate — otherwise
autogenerate tries to drop the SQL-defined table it stands for.
