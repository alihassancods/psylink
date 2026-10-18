-- 004_alert_delivery.sql — a delivery stamp, so one clinician is not emailed repeatedly.
--
-- The alert *row* is the record that a high-risk check-in happened; `emailed_at` records that a
-- human was actually pinged about it. Deduplicating on the delivery stamp rather than on the
-- row's creation time matters: several high check-ins inside one window should still each leave
-- a row (the clinician must see the count), but only the first one sends an email.

alter table public.alerts add column if not exists emailed_at timestamp with time zone;

comment on column public.alerts.emailed_at is
    'When a clinician was emailed about this alert. Null means the dashboard row exists but no mail went out.';

-- The dedupe lookup: "has this pair been emailed about recently?"
create index if not exists alerts_emailed_idx
    on public.alerts (clinician_id, patient_id, emailed_at desc);

-- Where to reach a clinician. Kept on `profiles` rather than reaching into Supabase's `auth`
-- schema so the same code runs against a local Postgres that has no auth at all, and so the
-- address a route reads is governed by the same row-level-security rules as everything else.
-- (auth.users remains the source of truth for login; this is a delivery address.)
alter table public.profiles add column if not exists email text;

comment on column public.profiles.email is
    'Delivery address for clinician alerts. Nullable; absence means dashboard-only.';

