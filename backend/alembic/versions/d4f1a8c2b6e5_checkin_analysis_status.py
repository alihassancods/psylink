"""checkin analysis status

Revision ID: d4f1a8c2b6e5
Revises: b7e4c9d1a2f3
Create Date: 2026-10-18 04:20:00.000000

Adds the columns the check-in pipeline needs: `analysis_status` (pending -> analyzed /
analysis_failed) and `transcript` (the patient-approved words that were analysed). The same
DDL now lives in supabase/migrations/001_schema.sql for fresh projects, so this revision is
the path for databases that were already migrated, and re-running it is a no-op.

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f1a8c2b6e5"
down_revision: Union[str, Sequence[str], None] = "b7e4c9d1a2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE_STATEMENTS = (
    """
    do $$
    begin
        if not exists (
            select 1 from pg_type t
            join pg_namespace n on n.oid = t.typnamespace
            where n.nspname = 'public' and t.typname = 'checkin_analysis_status'
        ) then
            create type public.checkin_analysis_status as enum ('pending', 'analyzed', 'analysis_failed');
        end if;
    end
    $$;
    """,
    """
    alter table public.checkins add column if not exists analysis_status
        public.checkin_analysis_status not null default 'pending';
    """,
    "alter table public.checkins add column if not exists transcript text;",
    """
    create index if not exists checkins_pending_idx
        on public.checkins (created_at)
        where analysis_status = 'pending';
    """,
)

DOWNGRADE_STATEMENTS = (
    "drop index if exists public.checkins_pending_idx;",
    "alter table public.checkins drop column if exists transcript;",
    "alter table public.checkins drop column if exists analysis_status;",
    "drop type if exists public.checkin_analysis_status;",
)


def upgrade() -> None:
    """Apply the guarded DDL one statement at a time."""
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """Remove the columns and the enum again."""
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
