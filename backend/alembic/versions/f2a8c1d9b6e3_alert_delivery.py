"""alert delivery columns

Revision ID: f2a8c1d9b6e3
Revises: e7b3d9c4a1f8
Create Date: 2026-10-18 06:50:00.000000

Applies supabase/migrations/004_alert_delivery.sql: `alerts.emailed_at` (the delivery stamp the
6-hour dedupe reads) and `profiles.email` (where a clinician is reachable). Without this
revision a database built from scratch by CI has neither, so a fresh checkout silently differs
from one that was migrated by hand.

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

from app.services.sql_script import split_sql_statements

# revision identifiers, used by Alembic.
revision: str = 'f2a8c1d9b6e3'
down_revision: Union[str, Sequence[str], None] = 'e7b3d9c4a1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
SQL_FILES = ("004_alert_delivery.sql",)


def upgrade() -> None:
    """Apply the canonical SQL, one statement at a time."""
    for name in SQL_FILES:
        script = (MIGRATIONS / name).read_text(encoding="utf-8")
        for statement in split_sql_statements(script):
            op.execute(statement)


def downgrade() -> None:
    """Drop the delivery columns. Rows written through them are lost with them."""
    statements = (
        "alter table public.alerts drop column if exists emailed_at;",
        "drop index if exists public.alerts_emailed_idx;",
        "alter table public.profiles drop column if exists email;",
    )
    for statement in statements:
        op.execute(statement)
