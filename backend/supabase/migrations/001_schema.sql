-- 001_schema.sql — core tables for the check-in → analysis → alert pipeline.
--
-- This directory is the canonical schema source. Apply it to a Supabase project with
-- `supabase db push`, or locally with `uv run alembic upgrade head` (the head revision runs
-- these two files in order). Every statement is idempotent, so either path can be re-run.

-- ── enums ───────────────────────────────────────────────────────────────────────────────────
-- user_role already exists from the pre-Supabase alembic history; the guards keep this file
-- safe on both a fresh database and the existing one.
do $$
begin
    if not exists (
        select 1 from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public' and t.typname = 'user_role'
    ) then
        create type public.user_role as enum ('patient', 'clinician');
    end if;

    if not exists (
        select 1 from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'public' and t.typname = 'risk_level'
    ) then
        create type public.risk_level as enum ('low', 'medium', 'high');
    end if;
end
$$;

-- ── profiles ────────────────────────────────────────────────────────────────────────────────
-- Application-side identity, keyed by the auth user id carried in the JWT `sub` claim. The id
-- matches the column shape the earlier alembic revision created, so re-running is a no-op.
--
-- No FK to auth.users on purpose: on a hosted project GoTrue owns that table and a backfill
-- constraint would reject rows already seeded without a matching auth user. Identity is
-- enforced by the verified token instead (see app/services/db.py).
create table if not exists public.profiles (
    id           uuid primary key,
    role         public.user_role,
    display_name character varying(120),
    created_at   timestamp with time zone not null default now()
);

comment on table public.profiles is
    'One row per auth user. role drives every RLS policy, so it is read from here, never from a token claim.';

-- ── consents ────────────────────────────────────────────────────────────────────────────────
-- The patient↔clinician link. A consent is active while revoked_at is null; revoking keeps the
-- row so there is an audit trail, and re-granting inserts a fresh one (or clears revoked_at).
create table if not exists public.consents (
    id           uuid primary key default gen_random_uuid(),
    patient_id   uuid not null references public.profiles (id) on delete cascade,
    clinician_id uuid not null references public.profiles (id) on delete cascade,
    granted_at   timestamp with time zone not null default now(),
    revoked_at   timestamp with time zone,
    created_at   timestamp with time zone not null default now(),
    constraint consents_not_self_referential
        check (patient_id <> clinician_id)
);

-- Managed as a guarded alter rather than inline, so re-running this file can correct a database
-- that already has an older definition of it.
--
-- The one-minute tolerance is not sloppiness: `granted_at` is stamped by Postgres while
-- `revoked_at` arrives from the application clock, and the two disagree freely down to the
-- microsecond. A strict `>=` would reject a revoke issued immediately after the grant. Anything
-- beyond a minute of backwards drift is a genuine data error, and is still rejected.
alter table public.consents drop constraint if exists consents_not_revoked_before_granted;
alter table public.consents add constraint consents_not_revoked_before_granted
    check (revoked_at is null or revoked_at >= granted_at - interval '1 minute');

-- One live consent per pair; history rows (revoked ones) stay unlimited.
create unique index if not exists consents_active_pair_key
    on public.consents (patient_id, clinician_id)
    where revoked_at is null;
create index if not exists consents_patient_id_idx
    on public.consents (patient_id);
create index if not exists consents_clinician_live_idx
    on public.consents (clinician_id)
    where revoked_at is null;

comment on table public.consents is
    'Patient grants a clinician access. revoked_at is null means active; RLS reads this table.';

-- ── checkins ──────────────────────────────────────────────────────────────────────────────────
-- Patient-authored input. `answers` holds the questionnaire payload so the form can change
-- without a migration; the shape is validated in the API layer, not here.
create table if not exists public.checkins (
    id         uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.profiles (id) on delete cascade,
    created_at timestamp with time zone not null default now(),
    answers    jsonb not null default '{}'::jsonb,
    note       text,
    constraint checkins_answers_are_objects check (jsonb_typeof(answers) = 'object')
);

create index if not exists checkins_patient_created_idx
    on public.checkins (patient_id, created_at desc);

comment on table public.checkins is 'Daily patient check-in; the newest rows drive analysis.';

-- ── analyses ───────────────────────────────────────────────────────────────────────────────────
-- Written by the analysis pipeline through service_client(); nobody reading through
-- user_client() may create or edit one, which keeps risk_level tamper-proof.
create table if not exists public.analyses (
    id         uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.profiles (id) on delete cascade,
    checkin_id uuid references public.checkins (id) on delete set null,
    created_at timestamp with time zone not null default now(),
    model      text,
    summary    text not null default '',
    risk       public.risk_level not null default 'low',
    signals    jsonb not null default '{}'::jsonb
);

create index if not exists analyses_patient_created_idx
    on public.analyses (patient_id, created_at desc);

comment on table public.analyses is 'Model output for a patient; service-role writes only.';

-- ── alerts ───────────────────────────────────────────────────────────────────────────────────
-- Raised for one clinician about one patient. Acknowledging sets acknowledged_at (and
-- acknowledged_by); an unacknowledged alert keeps acknowledged_at null.
create table if not exists public.alerts (
    id               uuid primary key default gen_random_uuid(),
    patient_id       uuid not null references public.profiles (id) on delete cascade,
    clinician_id     uuid not null references public.profiles (id) on delete cascade,
    analysis_id      uuid references public.analyses (id) on delete set null,
    created_at       timestamp with time zone not null default now(),
    severity         public.risk_level not null default 'high',
    message          text not null,
    acknowledged_at  timestamp with time zone,
    acknowledged_by  uuid references public.profiles (id) on delete set null,
    constraint alerts_acknowledged_by_consistent
        check (acknowledged_at is null or acknowledged_by is not null)
);

create index if not exists alerts_clinician_ack_idx
    on public.alerts (clinician_id, acknowledged_at);
create index if not exists alerts_patient_created_idx
    on public.alerts (patient_id, created_at desc);

comment on table public.alerts is 'Clinician work queue; created by the pipeline, acknowledged by the clinician.';
