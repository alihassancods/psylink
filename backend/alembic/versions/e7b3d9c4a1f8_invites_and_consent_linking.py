"""invites and consent linking

Revision ID: e7b3d9c4a1f8
Revises: d4f1a8c2b6e5
Create Date: 2026-10-18 05:40:00.000000

Applies supabase/migrations/003_invites.sql — the invites table, the app.redeem_invite()
function, and the patient-side policy that lets someone see which clinician they share data
with. The same file is pushed to a hosted project with `supabase db push`, so this revision is
the local path; it re-runs the whole file because every statement in it is idempotent.

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

from app.services.sql_script import split_sql_statements

# revision identifiers, used by Alembic.
revision: str = 'e7b3d9c4a1f8'
down_revision: Union[str, Sequence[str], None] = 'd4f1a8c2b6e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
SQL_FILES = ("003_invites.sql",)


def upgrade() -> None:
    """Apply the canonical SQL, one statement at a time."""
    for name in SQL_FILES:
        script = (MIGRATIONS / name).read_text(encoding="utf-8")
        for statement in split_sql_statements(script):
            op.execute(statement)


def downgrade() -> None:
    """Remove the invite surface. Consents already granted are kept — they are the record."""
    statements = (
        "drop policy if exists profiles_select_consenting_clinician on public.profiles;",
        "drop function if exists app.redeem_invite(text);",
        "drop table if exists public.invites;",
    )
    for statement in statements:
        op.execute(statement)
