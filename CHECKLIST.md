# Bridge: Build Progress

Last updated: 2026-10-18 14:05 PKT

Legend: [ ] not started, [x] done. Add "(partial)" after anything half-finished.

> Status is measured against the repository and the running databases, not against intentions. An
> item is `[x]` only when the code exists, is committed, and is covered by a passing test.
> **406 tests pass** (`uv run pytest`), with 3 live-provider tests skipped behind `RUN_LIVE_TESTS`.

## 0. Setup
- [ ] GitHub repo created (public) — **BLOCKED**: `git remote -v` is empty. Needs your repo, then
  `git remote add origin … && git push -u origin main`. Local git has 17 commits.
- [x] Supabase project created — `.env` points at a live hosted project
- [ ] AssemblyAI API key — **BLOCKED**: `ASSEMBLYAI_API_KEY` is empty. Speech-to-text is complete
  and tested against a fake SDK, but has never made a real call.
- [ ] Command Code API key (plan has API access) — **BLOCKED for `backend/.env`** (it is empty
  there). The pipeline has been verified live four times using a local CLI key; the deployed
  backend needs its own.
- [ ] Resend API key — **BLOCKED**: not in `.env`. Email alerts are built and degrade to
  dashboard-only without it.
- [ ] Render account (backend) and Vercel account (frontend) — **BLOCKED**: needs your accounts.
- [x] `docs/PLAN.md` saved in the repo — problem, architecture, load-bearing decisions, the
  mistakes worth remembering, and the cut list
- [x] `.env.example` files committed; real `.env` files git-ignored — `backend/.env.example`
  tracked and now documents all 13 settings; `backend/.env` verified absent from `git ls-files`

## 1. Backend (FastAPI, `backend/`)
- [x] 1.1 Foundation: app factory, config, CORS, error handler, `/health` — CORS comes from
  `FRONTEND_ORIGIN`; the 500 handler returns the standard shape and never echoes exception text
  (verified: unauthenticated → 401, preflight → correct `allow-origin`, from inside the container)
- [x] 1.2 Auth: Supabase JWT verification, `require_role`
- [x] 1.3 Database: schema, RLS policies, RLS tests — four canonical SQL files now (001–004), 17
  policies, proven on a **from-scratch** database
- [x] 1.4 Keyword safety screen (20+ tests) — **81 tests**: 47 must-fire phrases against 29 that must stay quiet
- [x] 1.5 LLM client (Command Code via OpenAI SDK) — JSON-mode probe, fallback model, and
  truncation/empty-reply detection
- [x] 1.6 Combined analysis pipeline (screen + LLM + guardrails + final risk) — one LLM call
- [x] 1.7 `POST /api/transcribe` (AssemblyAI, transcript deleted after use) — deletion proven on
  every path including timeout; no temp file is ever written
- [x] 1.8 `POST /api/checkins` (save first, analyze, return result) — a check-in survives a dead
  model, a garbled model, and a failed status write
- [x] 1.9 Consent and clinician linking (`/consent`, `/link`) — codes stored as sha256 only,
  single-use but idempotent for their redeemer; `app.redeem_invite` consumes, the patient's own
  RLS policy grants
- [x] 1.10 Alerts: Resend email, 6-hour dedupe, acknowledge — **no patient content in any email**;
  dedupe is on delivery, so every high check-in keeps its alert row while only the first mails
- [x] 1.11 Patient history: list and delete own check-ins — delete removes the analysis **first**,
  because the FK would otherwise orphan a summary of withdrawn words
- [x] 1.12 Clinician routes: patient list, trends, check-in detail — all reads through the caller's
  role; unconsented patients are invisible, not merely forbidden
- [x] 1.13 Demo login and seed data (1 clinician, 3 patients, 14 days) — `scripts/seed_demo.py`,
  deterministic and idempotent; **auth users still need creating** (`--create-auth-users`, or the
  dashboard) before anyone can sign in
- [x] 1.14 Safety evaluation script and `docs/eval-results.md` — 49-item labelled synthetic
  corpus, offline floor metrics + live pipeline metrics, and **CI fails if floor recall drops below
  80%**
- [x] 1.15 Dockerfile, CI (pytest on push), backend README — image builds, runs as non-root, serves
  all 14 routes; CI verified by running the full suite against a freshly migrated database

## 2. Frontend (Next.js, `frontend/`)
**BLOCKED — there is no `frontend/` directory in this repository.** `ls` at the root returns only
`backend/`, `docs/`, and `.github/`. None of 2.1–2.13 can be done here. The contract they depend
on is written up in `backend/README.md` → "Frontend contract", including the exact error codes that
should trigger the typed-input fallback and the meaning of `analysis_failed`.

- [ ] 2.1 Login and signup with demo buttons
- [ ] 2.2 Consent screen and invite-code linking — backend is ready (`/api/link`, `/api/consent`)
- [ ] 2.3 Recorder (MediaRecorder, timer, typed fallback) — backend is ready (`/api/transcribe`)
- [ ] 2.4 Editable transcript review and submit
- [ ] 2.5 Result screen with crisis resources card — driven by `show_crisis_resources`
- [ ] 2.6 "Need help now?" link on every patient screen
- [ ] 2.7 Patient history and settings (revoke consent, delete) — backend is ready
- [ ] 2.8 Clinician patient list with risk badges — backend is ready (`GET /api/patients`)
- [ ] 2.9 Patient detail: trend charts and timeline — backend is ready (`/trend?days=`)
- [ ] 2.10 Check-in detail with evidence quote highlighted — backend is ready
- [ ] 2.11 Alerts panel with acknowledge — backend is ready (`/api/alerts`)
- [ ] 2.12 Empty, loading, and error states
- [ ] 2.13 Mobile layout (360px) and accessibility pass

## 3. Safety (must not be cut)
- [x] Keyword floor can never be lowered by the LLM — `final_risk = higher(keyword, llm)`; tested,
  and re-confirmed live: **19/19 corpus high-risk items reported high**
- [x] Failed analysis defaults to "moderate" and shows crisis resources — `risk_source=fallback`
- [x] Evidence quote verified against the transcript — exact substring or dropped + confidence low
- [x] No diagnostic wording in summaries — blocklist, one corrective retry, then the reply is
  discarded whole
- [x] No audio stored; no transcripts in logs — verified by test, including the SQLAlchemy
  parameter-echo path that `logger.exception()` would have leaked
- [x] Consent required before transcribe and check-in; revoke blocks clinician access — `/api/
  transcribe` 403s without a live consent, and revocation is proven to close the roster, the
  trend, the detail, the alert history, and transcription
- [ ] "AI-generated, verify with the patient" label on clinician screens — **BLOCKED**: frontend
  (2.8–2.11). The data it needs (`risk_source`, `confidence`, `model`) is already in the API.
- [ ] "Not emergency care" notice in onboarding and footer — **BLOCKED**: frontend (2.2)

## 4. Deploy and test
**BLOCKED as a group.** Nothing is deployed; every item needs your accounts, two missing API keys,
and — for 4.1 — the schema drift below fixed first.

- [ ] Backend deployed on Render; `/health` returns 200 — **the image is ready and verified
  locally**; also note the hosted-schema blocker below
- [ ] Frontend deployed on Vercel
- [ ] `FRONTEND_ORIGIN` and `NEXT_PUBLIC_API_URL` set; no CORS errors — backend reads
  `FRONTEND_ORIGIN` today and was verified against a live preflight
- [ ] Full flow tested on a phone (record, transcribe, submit, clinician view)
- [ ] Alert email received at the demo clinician address
- [ ] Demo patient and demo clinician logins work on the live site — needs 1.13's auth users
- [ ] Backend woken up (`/health`) shortly before judging or recording

### ⚠ Blocker: the hosted Supabase schema is behind the code

Verified against both databases just now. The hosted project has `invites`, `app.redeem_invite`,
`alerts.emailed_at`, `profiles.email` and all 17 policies — but **`checkins.analysis_status` and
`checkins.transcript` are missing**, and they are not optional: `POST /api/checkins` writes both
and will 500 in production. The local docker database has them, which is why the suite is green.

Run this in the Supabase SQL editor (idempotent):

```sql
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

alter table public.checkins add column if not exists analysis_status
    public.checkin_analysis_status not null default 'pending';
alter table public.checkins add column if not exists transcript text;

create index if not exists checkins_pending_idx
    on public.checkins (created_at)
    where analysis_status = 'pending';
```

Confirm with:

```sql
select column_name from information_schema.columns
where table_schema='public' and table_name='checkins' order by ordinal_position;
```

…which should end with `analysis_status` and `transcript`. Or verify it yourself, read-only:

```bash
uv run python scripts/check_schema.py        # exits 1 and names every missing object
```

Confirmed with that tool just now: hosted is missing exactly those three objects
(`checkins.analysis_status`, `checkins.transcript`, and the `checkin_analysis_status` enum type);
local has all of them plus everything else.

**How this happened, stated plainly:** you ran the first SQL block in Supabase, but my idempotency
checks — written against `app.db.session.engine`, which reads `DATABASE_URL` from your `.env`
(the transaction pooler) rather than the local test database — applied the *later* migrations to
your **hosted project** without me checking where they were landing. That is why the newer objects
exist hosted and the older ones don't. Both writes were additive and idempotent DDL, so nothing
hosted was damaged, but I should have confirmed the target first and did not.

## 5. Submission
- [x] README: problem, features, architecture, setup, env vars — repo-root `README.md` now states
  the problem, the feature set, the safety mechanisms, quick start, and env vars, and links into
  `backend/README.md` (architecture, 13-setting config table, RLS, endpoints, tests, container)
- [x] README: safety design, eval results, limitations, "before production" list — safety design in
  `backend/README.md`, numbers in `docs/eval-results.md`, and both lists written
- [ ] 3 to 5 screenshots — **BLOCKED**: needs the running frontend
- [ ] 2-minute demo video (and a backup recording) — **BLOCKED**: needs the deployed app
- [ ] Devpost write-up — **BLOCKED**: needs your Devpost account
- [ ] Demo credentials in submission notes — **BLOCKED**: the four emails are fixed and printed by
  `scripts/seed_demo.py`, but the auth users must be created first
- [x] Statement that all demo data is synthetic — in `backend/README.md` (Privacy, Demo data),
  `docs/PLAN.md`, and `docs/eval-results.md`; the corpus and seeder are labelled invented
- [ ] Final check: live link opens in a private window on a phone — **BLOCKED**: nothing deployed
- [ ] Submitted before the deadline (Oct 18, 11:45pm PDT)

## Cut list (if short on time, in this order)
1. Safety eval script — *built, offline, and wired into CI; cutting it loses the recall gate*
2. Rate limiting — *built; in-process, so the ceiling is per-worker*
3. Email alerts (keep the dashboard alert) — *built and degrades to dashboard-only on its own*
4. History delete — *built*
5. Trends date filter — *built (`?days=`)*

Nothing on the cut list still needs cutting: all five are implemented and tested. The remaining
work is entirely in sections 0, 2, 4, and 5 — accounts, the frontend, and the schema fix above.

---

## What I need from you

| # | Need | Unblocks |
| --- | --- | --- |
| 1 | **Run the SQL block in §4** on Supabase | 4.1, any production check-in |
| 2 | GitHub repo → `git remote add origin` + push | 0.1, CI actually running |
| 3 | `ASSEMBLYAI_API_KEY` in `backend/.env` | 0.3, live transcription, `RUN_LIVE_TESTS=1` |
| 4 | `COMMANDCODE_API_KEY` in `backend/.env` | 0.4, deployed analysis |
| 5 | Resend key + verified sender domain → `RESEND_API_KEY`, `ALERT_EMAIL_FROM` | 0.5, 1.10 email, 4.5 |
| 6 | Supabase auth users for the 4 demo emails (`scripts/seed_demo.py --create-auth-users`) | 4.6, demo credentials |
| 7 | Render + Vercel projects, and a `frontend/` | all of 2, all of 4 |
| 8 | `docker compose up -d db && uv run alembic upgrade head` locally, if you want the dev DB current | running the suite yourself |

One caveat worth knowing before you deploy: alembic **cannot** reach the hosted project through the
`6543` transaction-mode pooler in your `.env` (it prepares statements; the pooler multiplexes
them). Use the session-mode pooler on `5432` for migrations, or keep pushing SQL through the
dashboard as we have been.
