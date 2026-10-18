-- 003_invites.sql — clinician invite codes, so consent can be granted without shared secrets.
--
-- The flow the UI needs: a clinician creates a short code, the patient enters it, and that is
-- what creates the consent row. The code is the only thing that travels, so the table stores a
-- hash of it — a database leak would hand over hashes of codes that have most likely expired
-- anyway, not live links to patients' mental-health records.
--
-- Idempotent like the other files: re-running it, or pushing it to a project where Alembic
-- already applied it, changes nothing.

create table if not exists public.invites (
    id           uuid primary key default gen_random_uuid(),
    clinician_id uuid not null references public.profiles (id) on delete cascade,
    code_hash    text not null unique,
    created_at   timestamp with time zone not null default now(),
    expires_at   timestamp with time zone not null,
    used_at      timestamp with time zone,
    used_by      uuid references public.profiles (id) on delete set null,
    constraint invites_expires_after_creation check (expires_at > created_at),
    constraint invites_used_by_consistent check (used_at is null or used_by is not null)
);

create index if not exists invites_clinician_idx
    on public.invites (clinician_id, created_at desc);

comment on table public.invites is
    'Short-lived clinician invite codes. Only the hash is stored; the code itself is shown once.';
comment on column public.invites.code_hash is
    'sha256 hex of the code. The plaintext never reaches the database.';

-- Redeeming is the one operation a patient must be able to perform on a row they cannot read.
-- Rather than opening the table to them, this function does the lookup as its owner, checks the
-- code is live and unconsumed, consumes it, and returns whose invite it was — or null.
--
-- Returning a clinician_id is not enough to grant access: the caller still has to insert the
-- consent row through its own RLS policy, which only lets a patient consent to share *their*
-- data. So this function can consume an invite but cannot create access on its own.
create or replace function app.redeem_invite(p_code_hash text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    invite public.invites%rowtype;
begin
    -- p_code_hash arrives from a caller who already knows a code; nothing here logs or echoes it.
    if p_code_hash is null or length(p_code_hash) <> 64 then
        return null;
    end if;

    -- `for update` so two patients redeeming the same code at once cannot both win.
    select * into invite
        from public.invites
        where code_hash = p_code_hash
          and expires_at > now()
        for update;

    if not found then
        return null;
    end if;

    -- A clinician must not be able to link themselves, whatever the route layer allowed.
    if invite.clinician_id = app.current_user_id() then
        return null;
    end if;

    if invite.used_at is not null then
        -- Consumed already. The original redeemer may replay it — a retried request after a
        -- dropped connection should not tell a patient their link failed when it worked.
        -- Anyone else still gets nothing.
        if invite.used_by = app.current_user_id() then
            return invite.clinician_id;
        end if;
        return null;
    end if;

    update public.invites
        set used_at = now(), used_by = app.current_user_id()
        where id = invite.id;

    return invite.clinician_id;
end
$$;

grant execute on function app.redeem_invite(text) to authenticated;

comment on function app.redeem_invite(text) is
    'Consumes a live, unused invite hash and returns its clinician_id, or null. SECURITY DEFINER: '
    'it is the only path that can see an invite row as a patient, and it grants nothing by itself.';

-- ── access rules ──────────────────────────────────────────────────────────────────────────────
-- RLS enabled but deliberately not FORCED: `app.redeem_invite` is SECURITY DEFINER and runs as
-- the table owner, which is exempt only while the table is unfixed. Forcing it would stop the
-- function from seeing the row it has to consume — the same reason `service_client` works.
alter table public.invites enable row level security;

-- `authenticated` gets no UPDATE grant at all: consuming an invite happens inside the definer
-- function, never from route code holding a patient's token.
grant select, insert on table public.invites to authenticated;
revoke update, delete on table public.invites from authenticated;

drop policy if exists invites_select_own on public.invites;
create policy invites_select_own on public.invites
    for select to authenticated
    using (app.is_clinician() and clinician_id = app.current_user_id());

drop policy if exists invites_insert_own on public.invites;
create policy invites_insert_own on public.invites
    for insert to authenticated
    with check (app.is_clinician() and clinician_id = app.current_user_id());

-- No update, delete, or patient-facing select policy: a patient redeems through
-- app.redeem_invite() and never reads the row. Revoking a consent is not deleting an invite.

-- A patient granted access to a clinician should be able to see who that is — today they can
-- only see their own profile row. Scoped to the live grant, so revoking hides this too.
drop policy if exists profiles_select_consenting_clinician on public.profiles;
create policy profiles_select_consenting_clinician on public.profiles
    for select to authenticated
    using (
        app.is_patient()
        and id in (
            select c.clinician_id
            from public.consents c
            where c.patient_id = app.current_user_id()
              and c.revoked_at is null
        )
    );

comment on policy profiles_select_consenting_clinician on public.profiles is
    'A patient may read the profile of a clinician they currently share data with.';
