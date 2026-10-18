# Bridge: Build Progress

Last updated: 2026-10-18 17:00 PKT

Legend: [ ] not started, [x] done. Add "(partial)" after anything half-finished.

> Status is measured against the repository, not against intentions: an item is `[x]` only when
> the code exists, is committed, and is covered by a passing test. Items that need an account, a
> paid plan, or a credential I do not have are marked **BLOCKED** with the exact thing needed.

## 0. Setup
- [ ] GitHub repo created (public) — **BLOCKED**: no remote is configured (`git remote -v` is empty). Needs your repo. Local git exists with 10 commits.
- [x] Supabase project created — `.env` points at a live hosted project (`postgres.<ref>.supabase.com`)
- [ ] AssemblyAI API key — **BLOCKED**: `ASSEMBLYAI_API_KEY` is empty in `backend/.env`. Speech-to-text is fully implemented and tested against a fake SDK, but has never made a real call.
- [ ] Command Code API key (plan has API access) — **BLOCKED for the backend's own `.env`**: `COMMANDCODE_API_KEY` is empty there. The pipeline was verified live once using a local CLI key (4/4 runs); the deployed backend still needs its own key.
- [ ] Resend API key — **BLOCKED**: not created, not in `.env`. Email alerts are being implemented behind this key and degrade to dashboard-only without it.
- [ ] Render account (backend) and Vercel account (frontend) — **BLOCKED**: needs your accounts.
- [ ] `docs/PLAN.md` saved in the repo
- [x] `.env.example` files committed; real `.env` files git-ignored — `backend/.env.example` is tracked, `backend/.env` is ignored and verified absent from `git ls-files`

## 1. Backend (FastAPI, `backend/`)
- [ ] 1.1 Foundation: app factory, config, CORS, error handler, `/health` — **partial**. `/health`, `/health/db`, `/auth/me`, and `Settings` exist; CORS middleware and the standard-shape error handler are not in `app/main.py` yet.
- [x] 1.2 Auth: Supabase JWT verification, `require_role` — RS256-via-JWKS or HS256, algorithm from config never from the token, role read from `profiles` not from a claim (`app/core/security.py`, `app/core/deps.py`)
- [x] 1.3 Database: schema, RLS policies, RLS tests — `supabase/migrations/001_schema.sql` + `002_rls.sql`, four suites under `tests/rls/`
- [x] 1.4 Keyword safety screen (20+ tests) — `app/services/analysis/keywords.py`, 75 tests (36 must-fire, 28 must-stay-silent, plus clause/negation cases)
- [x] 1.5 LLM client (Command Code via OpenAI SDK) — `app/services/ai/llm_client.py`, JSON-mode probe, fallback model, truncation retry; 16 tests + a live smoke test
- [x] 1.6 Combined analysis pipeline (screen + LLM + guardrails + final risk) — `app/services/analysis/pipeline.py`, one LLM call, floor cannot be lowered; 15 tests
- [x] 1.7 `POST /api/transcribe` (AssemblyAI, transcript deleted after use) — deletion verified on every path including timeout and failure; 27 tests
- [x] 1.8 `POST /api/checkins` (save first, analyze, return result) — `pending → analyzed/analysis_failed`; a check-in survives a dead model, a garbled model, and a failed status write; 24 tests
- [ ] 1.9 Consent and clinician linking (`/consent`, `/link`)
- [ ] 1.10 Alerts: Resend email, 6-hour dedupe, acknowledge
- [ ] 1.11 Patient history: list and delete own check-ins
- [ ] 1.12 Clinician routes: patient list, trends, check-in detail
- [ ] 1.13 Demo login and seed data (1 clinician, 3 patients, 14 days)
- [ ] 1.14 Safety evaluation script and `docs/eval-results.md` (cut first if short on time)
- [ ] 1.15 Dockerfile, CI (pytest on push), backend README — **partial**: `backend/README.md` exists and is thorough; no Dockerfile, no `.github/workflows`

## 2. Frontend (Next.js, `frontend/`)
**BLOCKED — there is no `frontend/` directory in this repository.** `ls` at the root returns only
`backend/`. None of 2.1–2.13 can be checked here; the backend contract they depend on is
documented in `backend/README.md` → "Frontend contract".

- [ ] 2.1 Login and signup with demo buttons
- [ ] 2.2 Consent screen and invite-code linking
- [ ] 2.3 Recorder (MediaRecorder, timer, typed fallback)
- [ ] 2.4 Editable transcript review and submit
- [ ] 2.5 Result screen with crisis resources card
- [ ] 2.6 "Need help now?" link on every patient screen
- [ ] 2.7 Patient history and settings (revoke consent, delete)
- [ ] 2.8 Clinician patient list with risk badges
- [ ] 2.9 Patient detail: trend charts and timeline
- [ ] 2.10 Check-in detail with evidence quote highlighted
- [ ] 2.11 Alerts panel with acknowledge
- [ ] 2.12 Empty, loading, and error states
- [ ] 2.13 Mobile layout (360px) and accessibility pass

## 3. Safety (must not be cut)
- [x] Keyword floor can never be lowered by the LLM — `final_risk = higher(keyword, llm)`; test `test_keyword_high_beats_llm_low`
- [x] Failed analysis defaults to "moderate" and shows crisis resources — `risk_source="fallback"`; tests in `test_pipeline.py` and `test_checkins_api.py`
- [x] Evidence quote verified against the transcript — exact-substring check, else dropped + confidence "low"; `test_fabricated_evidence_quote_is_removed_and_confidence_dropped`
- [x] No diagnostic wording in summaries — blocklist, one corrective retry, then the whole reply is discarded; `test_diagnostic_summary_after_retry_discards_the_analysis`
- [x] No audio stored; no transcripts in logs — bytes go to the SDK as memory (no temp file at all), and database errors are logged by exception class only because SQLAlchemy echoes bound parameters; `test_a_database_error_does_not_log_the_transcript`
- [ ] Consent required before transcribe and check-in; revoke blocks clinician access — **partial**: `/api/transcribe` requires an active consent (403 without) and revocation is proven to hide history in `tests/rls/test_clinician_consent.py`; the *grant/revoke endpoints* are item 1.9.
- [ ] "AI-generated, verify with the patient" label on clinician screens — **BLOCKED**: frontend (2.8–2.11)
- [ ] "Not emergency care" notice in onboarding and footer — **BLOCKED**: frontend (2.2)

## 4. Deploy and test
**BLOCKED as a group — every item here needs your Render/Vercel accounts and the two missing API
keys.** Nothing is deployed yet; no `Dockerfile` exists (1.15).

- [ ] Backend deployed on Render; `/health` returns 200
- [ ] Frontend deployed on Vercel
- [ ] `FRONTEND_ORIGIN` and `NEXT_PUBLIC_API_URL` set; no CORS errors
- [ ] Full flow tested on a phone (record, transcribe, submit, clinician view)
- [ ] Alert email received at the demo clinician address
- [ ] Demo patient and demo clinician logins work on the live site
- [ ] Backend woken up (`/health`) shortly before judging or recording

## 5. Submission
- [ ] README: problem, features, architecture, setup, env vars — **partial**: `backend/README.md` covers architecture, setup, config table, RLS, tests; the hackathon-facing "problem / features" framing is missing
- [ ] README: safety design, eval results, limitations, "before production" list — **partial**: safety design is documented; eval results (1.14), limitations, and the before-production list are not
- [ ] 3 to 5 screenshots — **BLOCKED**: needs the running frontend
- [ ] 2-minute demo video (and a backup recording) — **BLOCKED**: needs the deployed app
- [ ] Devpost write-up — **BLOCKED**: needs your Devpost account
- [ ] Demo credentials in submission notes — **BLOCKED**: needs the demo logins (1.13) and your Supabase project
- [ ] Statement that all demo data is synthetic — in `backend/README.md` → Privacy; needs repeating in the submission text
- [ ] Final check: live link opens in a private window on a phone — **BLOCKED**: nothing is deployed
- [ ] Submitted before the deadline (Oct 18, 11:45pm PDT)

## Cut list (if short on time, in this order)
1. Safety eval script
2. Rate limiting — *already built and tested (`app/core/ratelimit.py`); do not cut*
3. Email alerts (keep the dashboard alert)
4. History delete
5. Trends date filter

---

## What I need from you to close the rest

| Need | Unblocks |
| --- | --- |
| GitHub repo (then `git remote add origin … && git push`) | 0.1, CI actually running |
| `ASSEMBLYAI_API_KEY` in `backend/.env` | 0.3, live transcription, `RUN_LIVE_TESTS=1` |
| `COMMANDCODE_API_KEY` in `backend/.env` | 0.4, deployed analysis |
| Resend account + `RESEND_API_KEY` + a verified sender domain | 0.5, 1.10 email, 4.5 |
| Render + Vercel projects, and a `frontend/` repo | all of 2, all of 4 |
| Supabase SQL for the new tables (I will hand it over) | 1.9 |
