"""supabase schema and rls

Revision ID: b7e4c9d1a2f3
Revises: cc94754ebc39
Create Date: 2026-10-18 03:05:00.000000

The schema lives in supabase/migrations/*.sql so the same files can be pushed to a hosted
Supabase project with `supabase db push`. This revision is the local applier: it executes them
in filename order. They are written to be idempotent, so applying them here and pushing them
later does not conflict.

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

from app.services.sql_script import split_sql_statements

# revision identifiers, used by Alembic.
revision: str = 'b7e4c9d1a2f3'
down_revision: Union[str, Sequence[str], None] = 'cc94754ebc39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
SQL_FILES = ("001_schema.sql", "002_rls.sql")


def upgrade() -> None:
    """Apply the canonical SQL files, one statement at a time."""
    for name in SQL_FILES:
        script = (MIGRATIONS / name).read_text(encoding="utf-8")
        for statement in split_sql_statements(script):
            op.execute(statement)


def downgrade() -> None:
    """Undo this revision, leaving `profiles` and `user_role` to the revision before it.

    The `app` schema goes with cascade: its policies-bearing helper functions are what the
    policies depend on. The `anon`/`authenticated` roles stay, since a real Supabase project
    created them independently of this migration.
    """
    script = """
        drop table if exists public.alerts, public.analyses, public.checkins, public.consents cascade;
        drop type if exists public.risk_level;
        alter table if exists public.profiles disable row level security;
        drop schema if exists app cascade;
    """
    for statement in split_sql_statements(script):
        op.execute(statement)
