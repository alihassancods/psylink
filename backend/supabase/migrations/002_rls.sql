-- 002_rls.sql — row-level security: Postgres, not app code, decides who may see which row.
--
-- Model (same as Supabase): requests for a person run as the NOLOGIN role `authenticated` with
-- the verified JWT placed in the `request.jwt.claims` setting, while system writes run as the
-- table owner, which is exempt from RLS. app/services/db.py is the only thing that assumes the
-- role, and it verifies the signature before setting the claims — so a caller cannot choose
-- whose rows it reads.

-- ── roles ─────────────────────────────────────────────────────────────────────────────────────
-- Supabase creates these already; on a plain Postgres this block makes the file self-sufficient.
-- NOLOGIN on purpose: the app reaches them with `SET LOCAL ROLE`, never with a password.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated noinherit;
    end if;
end
$$;

-- ── identity helpers ──────────────────────────────────────────────────────────────────────────
create schema if not exists app;

-- One claim out of the request JWT, or null when there is no request. Tolerates the legacy
-- per-claim GUCs (request.jwt.claim.sub) that some Supabase versions set alongside the JSON one.
create or replace function app.jwt_claim(p_claim text)
returns text
language plpgsql
stable
set search_path = ''
as $$
declare
    v_claims jsonb;
begin
    begin
        v_claims := nullif(coalesce(current_setting('request.jwt.claims', true), ''), '')::jsonb;
    exception
        when others then v_claims := null;
    end;

    if v_claims is not null and jsonb_typeof(v_claims) = 'object' then
        return nullif(trim(v_claims ->> p_claim), '');
    end if;

    return nullif(current_setting('request.jwt.claim.' || p_claim, true), '');
end
$$;

-- The subject, and only if it is shaped like a uuid: a junk claim must yield null (deny) rather
-- than an error that leaks into the response.
create or replace function app.current_user_id()
returns uuid
language sql
stable
set search_path = ''
as $$
    select case
        when app.jwt_claim('sub') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        then app.jwt_claim('sub')::uuid
        else null
    end
$$;

-- SECURITY DEFINER for two reasons: it must read profiles through the owner to avoid recursing
-- into profiles' own policies, and it only ever reveals the caller's own single role value.
-- A `role` claim inside the token is never consulted — the database is the authority.
create or replace function app.current_user_role()
returns public.user_role
language sql
stable
security definer
set search_path = ''
as $$
    select p.role from public.profiles p where p.id = app.current_user_id()
$$;

create or replace function app.is_patient()
returns boolean
language sql
stable
set search_path = ''
as $$
    select app.current_user_role() = 'patient'::public.user_role
$$;

create or replace function app.is_clinician()
returns boolean
language sql
stable
set search_path = ''
as $$
    select app.current_user_role() = 'clinician'::public.user_role
$$;

-- The authorisation primitive every clinician-facing policy is built from: an active consent
-- between this caller and that patient. Passing p_clinician_id null resolves the caller from
-- the request, which is what the policies do; service-role code passes it explicitly.
-- Definer because it is an authority check, not a data read: it must see consent rows the
-- caller is not a party to in order to answer truthfully, and it returns only a boolean.
create or replace function app.has_active_consent(
    p_patient_id uuid,
    p_clinician_id uuid default null
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.consents c
        where c.patient_id = p_patient_id
          and c.clinician_id = coalesce(p_clinician_id, app.current_user_id())
          and c.revoked_at is null
    )
$$;

grant execute on function app.jwt_claim(text) to anon, authenticated;
grant execute on function app.current_user_id() to anon, authenticated;
grant execute on function app.current_user_role() to anon, authenticated;
grant execute on function app.is_patient() to anon, authenticated;
grant execute on function app.is_clinician() to anon, authenticated;
grant execute on function app.has_active_consent(uuid, uuid) to anon, authenticated;

comment on function app.has_active_consent(uuid, uuid) is
    'True while an unrevoked consent links the caller (or p_clinician_id) to p_patient_id.';

-- ── enable RLS on every table ─────────────────────────────────────────────────────────────────
-- No FORCE ROW LEVEL SECURITY: the owner is the service identity and must write freely
-- (creating alerts, seeding demo data). Everything a person does goes through `authenticated`.
alter table public.profiles   enable row level security;
alter table public.consents   enable row level security;
alter table public.checkins   enable row level security;
alter table public.analyses   enable row level security;
alter table public.alerts     enable row level security;

-- Privileges are the coarse half of the rule; policies are the fine half. `anon` gets nothing
-- at all, so an unauthenticated request is denied before RLS is even consulted.
grant usage on schema public to authenticated;
grant usage on schema app to anon, authenticated;

grant select, insert, update on table public.profiles   to authenticated;
grant select, insert, update on table public.consents   to authenticated;
grant select, insert, update, delete on table public.checkins to authenticated;
grant select on table public.analyses to authenticated;
grant select, update on table public.alerts to authenticated;

-- ── profiles ──────────────────────────────────────────────────────────────────────────────────
drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
    for select to authenticated
    using (id = app.current_user_id());

-- A clinician may see the patients they are currently caring for — needed to render the roster.
drop policy if exists profiles_select_consented on public.profiles;
create policy profiles_select_consented on public.profiles
    for select to authenticated
    using (app.is_clinician() and app.has_active_consent(id));

-- Onboarding: a caller may create their own profile, but only as a patient. Promoting anyone to
-- clinician is a service-role operation, so a signed-up attacker cannot grant themselves a role.
drop policy if exists profiles_insert_self on public.profiles;
create policy profiles_insert_self on public.profiles
    for insert to authenticated
    with check (id = app.current_user_id() and role is not distinct from 'patient'::public.user_role);

drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles
    for update to authenticated
    using (id = app.current_user_id())
    with check (
        id = app.current_user_id()
        -- a patient cannot write themselves into another role; the new row must still say patient
        and (app.is_clinician() or role is not distinct from 'patient'::public.user_role)
    );

-- ── consents ──────────────────────────────────────────────────────────────────────────────────
-- The patient owns the link: they grant it, they revoke it, they see it.
drop policy if exists consents_select_parties on public.consents;
create policy consents_select_parties on public.consents
    for select to authenticated
    using (patient_id = app.current_user_id() or clinician_id = app.current_user_id());

drop policy if exists consents_insert_patient on public.consents;
create policy consents_insert_patient on public.consents
    for insert to authenticated
    with check (patient_id = app.current_user_id() and revoked_at is null);

drop policy if exists consents_update_patient on public.consents;
create policy consents_update_patient on public.consents
    for update to authenticated
    using (patient_id = app.current_user_id())
    with check (patient_id = app.current_user_id());

-- No DELETE policy: revoking stamps revoked_at so the grant history survives.

-- ── checkins ──────────────────────────────────────────────────────────────────────────────────
drop policy if exists checkins_write_own on public.checkins;
create policy checkins_write_own on public.checkins
    for all to authenticated
    using (patient_id = app.current_user_id())
    with check (patient_id = app.current_user_id());

drop policy if exists checkins_read_consented on public.checkins;
create policy checkins_read_consented on public.checkins
    for select to authenticated
    using (app.is_clinician() and app.has_active_consent(patient_id));

-- ── analyses ───────────────────────────────────────────────────────────────────────────────────
-- Read-only through user_client for everyone: the pipeline writes them as the service role, so
-- no person can edit a risk verdict.
drop policy if exists analyses_read_own on public.analyses;
create policy analyses_read_own on public.analyses
    for select to authenticated
    using (patient_id = app.current_user_id());

drop policy if exists analyses_read_consented on public.analyses;
create policy analyses_read_consented on public.analyses
    for select to authenticated
    using (app.is_clinician() and app.has_active_consent(patient_id));

-- ── alerts ─────────────────────────────────────────────────────────────────────────────────────
drop policy if exists alerts_read_own on public.alerts;
create policy alerts_read_own on public.alerts
    for select to authenticated
    using (patient_id = app.current_user_id());

-- An alert is readable only while the consent behind it is still live, so revoking access also
-- hides the historical alerts — not just future rows.
drop policy if exists alerts_read_assigned on public.alerts;
create policy alerts_read_assigned on public.alerts
    for select to authenticated
    using (
        clinician_id = app.current_user_id()
        and app.is_clinician()
        and app.has_active_consent(patient_id)
    );

-- Acknowledging is the one write a clinician gets. RLS cannot pin individual columns, so the
-- route updates acknowledged_at/acknowledged_by only (see the API layer).
drop policy if exists alerts_acknowledge on public.alerts;
create policy alerts_acknowledge on public.alerts
    for update to authenticated
    using (
        clinician_id = app.current_user_id()
        and app.is_clinician()
        and app.has_active_consent(patient_id)
    )
    with check (
        clinician_id = app.current_user_id()
        and app.has_active_consent(patient_id)
    );
