"""Report which schema objects the code needs but the target database does not have.

    uv run python scripts/check_schema.py            # check DATABASE_URL from .env
    uv run python scripts/check_schema.py --local    # check the docker-compose database

Read-only. This exists because the deployed backend and the test suite can drift apart in
silence: the hosted project is managed through the Supabase dashboard (alembic cannot reach it
through the transaction-mode pooler), so a migration that landed locally may never have been
pushed — and the first sign would be a 500 on a patient's check-in, not a test failure.

Exit code 1 means the app would break on this database.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

#: Everything the routes and pipeline write or call, and the query that proves it exists.
REQUIRED: list[tuple[str, str]] = [
    ("table public.checkins", "select to_regclass('public.checkins') is not null"),
    ("table public.analyses", "select to_regclass('public.analyses') is not null"),
    ("table public.alerts", "select to_regclass('public.alerts') is not null"),
    ("table public.consents", "select to_regclass('public.consents') is not null"),
    ("table public.invites", "select to_regclass('public.invites') is not null"),
    (
        "checkins.analysis_status",
        "select count(*) from information_schema.columns "
        "where table_schema='public' and table_name='checkins' and column_name='analysis_status'",
    ),
    (
        "checkins.transcript",
        "select count(*) from information_schema.columns "
        "where table_schema='public' and table_name='checkins' and column_name='transcript'",
    ),
    (
        "alerts.emailed_at",
        "select count(*) from information_schema.columns "
        "where table_schema='public' and table_name='alerts' and column_name='emailed_at'",
    ),
    (
        "profiles.email",
        "select count(*) from information_schema.columns "
        "where table_schema='public' and table_name='profiles' and column_name='email'",
    ),
    (
        "type checkin_analysis_status",
        "select count(*) from pg_type t join pg_namespace n "
        "on n.oid=t.typnamespace where n.nspname='public' and t.typname='checkin_analysis_status'",
    ),
    (
        "function app.has_active_consent",
        "select count(*) from pg_proc p join pg_namespace n "
        "on n.oid=p.pronamespace where n.nspname='app' and p.proname='has_active_consent'",
    ),
    (
        "function app.redeem_invite",
        "select count(*) from pg_proc p join pg_namespace n "
        "on n.oid=p.pronamespace where n.nspname='app' and p.proname='redeem_invite'",
    ),
]

#: Policies the routes depend on for authorisation, by name.
LOCAL_URL = "postgresql+asyncpg://backend:backend@127.0.0.1:5433/backend"

POLICIES: list[str] = [
    "checkins_write_own",
    "checkins_read_consented",
    "consents_insert_patient",
    "alerts_read_assigned",
    "alerts_acknowledge",
    "invites_select_own",
    "invites_insert_own",
    "profiles_select_consenting_clinician",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the schema the app requires")
    parser.add_argument(
        "--local",
        action="store_true",
        help="check the docker-compose database instead of DATABASE_URL",
    )
    args = parser.parse_args()

    # A private engine, because app.db.session builds its own at import time from Settings.
    # Mutating DATABASE_URL here would come too late and quietly check the wrong database.
    url = LOCAL_URL if args.local else get_settings().database_url
    engine = create_async_engine(url)
    target = "docker-compose (local)" if args.local else "DATABASE_URL"

    missing: list[str] = []
    async with engine.connect() as conn:
        where = (await conn.execute(text("select current_database()"))).scalar()
        version = (await conn.execute(text("select current_setting('server_version')"))).scalar()
        print(f"checking {target}: database {where!r} (Postgres {version})\n")

        for label, query in REQUIRED:
            value = (await conn.execute(text(query))).scalar()
            present = bool(value)
            missing.append(label) if not present else None
            print(f"  {'OK  ' if present else 'MISS'}  {label}")

        rows = (
            await conn.execute(text("select policyname from pg_policies where schemaname='public'"))
        ).fetchall()
        existing = {row[0] for row in rows}
        for policy in POLICIES:
            present = policy in existing
            missing.append(f"policy {policy}") if not present else None
            print(f"  {'OK  ' if present else 'MISS'}  policy {policy}")

    await engine.dispose()

    if missing:
        print(
            f"\n{len(missing)} required object(s) missing: {', '.join(missing)}\n"
            "Apply the SQL in supabase/migrations/ (dashboard or `supabase db push`) before "
            "deploying — the app will 500 on the routes that touch these.",
            file=sys.stderr,
        )
        return 1
    print("\nall required schema objects present")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
