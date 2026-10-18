# Bridge

A daily voice check-in for people living with a mental-health condition, and a clinician queue
that ranks who needs attention — with a safety floor that a language model cannot lower.

**Not a clinical instrument.** Bridge describes what a patient said. It does not assess, diagnose,
or treat, and it says so on every screen.

> All demo data is **synthetic**. Every check-in text, patient name, and evaluation example in
> this repository was invented for the demo. No real patient audio or text exists here.

## How it works

```
patient records 30s of speech
   → POST /api/transcribe   (AssemblyAI; audio never stored, transcript deleted after reading)
   → patient edits the text and submits
   → POST /api/checkins     (stored first, then analysed)
   → keyword floor + ONE model call + guardrails  → final risk
   → clinician is alerted, patient sees crisis resources if warranted
```

The screen and the model run together, and they are not peers. **The keyword screen is a floor.**
`final_risk` is the higher of the two, so a model can raise risk and can never lower it. If the
model fails and the screen found nothing, the answer is `moderate` — "we could not tell" and
"they are fine" never look the same on this system.

## What makes it safe

| Mechanism | Why it exists |
| --- | --- |
| Deterministic keyword floor | Survives any model behaviour, including prompt injection. Clause-aware negation and idiom handling keep it credible. |
| `moderate` fail-safe | A dead model degrades toward support, not toward silence. |
| Verbatim evidence quotes | A quote is kept only if it is an exact substring of what the patient said, else dropped and confidence lowered. |
| Diagnostic-language blocklist | Summaries describe. A reply that names a condition is corrected once, then discarded. |
| Store before analysing | The check-in row is committed before any model runs. Nothing a patient submits is lost. |
| Row-level security | Postgres decides visibility. Revoking consent closes history, not just future rows. |
| `analyses` unwritable by users | A patient — or a request — cannot set their own risk level. |
| No patient content in logs | Sizes, counts, ids, exception class names. Includes database errors, whose text echoes bound parameters. |
| No audio on disk, remote transcript deleted | Memory-only upload; deletion runs on every path that got an id, including timeout. |

Measured, not asserted: **19/19 high-risk items in the evaluation corpus were reported `high`** by
the full pipeline. Numbers and honest limitations → [`docs/eval-results.md`](docs/eval-results.md).

## Where things live

| | |
| --- | --- |
| Backend — FastAPI, all setup, endpoints, RLS | [`backend/README.md`](backend/README.md) |
| Architecture and the decisions behind them | [`docs/PLAN.md`](docs/PLAN.md) |
| Safety evaluation and results | [`docs/eval-results.md`](docs/eval-results.md) |
| Build progress | [`CHECKLIST.md`](CHECKLIST.md) |
| Frontend | [`frontend/`](frontend/README.md) — Next.js app; its API contract is in `backend/README.md` → "Frontend contract" |

## Quick start

```bash
cd backend
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run pytest -q                     # 406 passed, 3 skipped (live provider tests)
uv run python scripts/seed_demo.py   # 1 clinician, 3 patients, 14 days of synthetic data
uv run fastapi dev app/main.py
```

Two external keys are needed for the full experience and both are optional by design — without
them the app degrades rather than failing:

```bash
ASSEMBLYAI_API_KEY=...     # /api/transcribe returns 503 without it; typing still works
COMMANDCODE_API_KEY=...    # analysis fails safe to "moderate"; the check-in is still stored
```

Configuration table (all 13 settings): [`backend/README.md`](backend/README.md#configuration).

## Model provider

Analysis calls go to the [Command Code Provider API](https://commandcode.ai/docs/provider) —
OpenAI-compatible Chat Completions — through the official `openai` SDK. Default model
`deepseek/deepseek-v4-flash`, overridable via `COMMANDCODE_MODEL` (verify ids against
`{base}/models`). One call per check-in produces the summary and the risk classification together.

One caveat found by live testing: on this provider `max_tokens` caps **reasoning** tokens too, so a
small budget silently returns empty or truncated JSON. The client detects both and retries once
with a larger budget. See `docs/PLAN.md` → "Things learned the hard way".

## Before production

This is a hackathon build. The full list is in
[`backend/README.md`](backend/README.md#before-this-went-anywhere-near-production); the short
version: clinical review of the corpus and thresholds, region-aware crisis routing, distributed
rate limiting, data-processing agreements with both providers, an audit trail on who read which
patient, and penetration testing of the invite flow.

## Frontend progress

`frontend/` is the Next.js (App Router) client. One step at a time; after each step run lint,
typecheck and tests, tick the box here, and commit. See [`frontend/README.md`](frontend/README.md)
for setup.

- [x] F1 Scaffold, Tailwind, shadcn, design tokens, .env.example
- [x] F2 Supabase auth, API client, role guards
- [x] F3 Login/signup with demo buttons
- [x] F4 Consent and invite-code screens
- [x] F5 Recorder with mic permission flow and typed fallback
- [x] F6 Transcript review and submit
- [x] F7 Result screen and crisis card
- [x] F8 "Need help now?" link and footer notice on all patient screens
- [x] F9 Patient history and settings (revoke, delete)
- [ ] F10 Clinician patient list with risk badges
- [ ] F11 Patient detail: trend charts and timeline
- [ ] F12 Check-in detail with evidence highlight and AI label
- [ ] F13 Alerts panel with acknowledge
- [ ] F14 Loading, empty, and error states everywhere
- [ ] F15 Mobile (360px) and accessibility pass
- [ ] F16 Unit tests and smoke test
- [ ] F17 Vercel deploy, tested on a phone

**Never cut:** consent, crisis card, "Need help now?" link, evidence highlight, demo buttons,
loading/error states. **Cut list, in order if short on time:** dark mode, Playwright test, history
delete, table toggle.

## Status

Backend: complete and tested — speech-to-text, the combined analysis pipeline, consent and
clinician linking, alerts with email and dedupe, patient history, clinician views, demo seeding,
safety evaluation wired into CI, and a verified container image.

Frontend, deployment, and submission: not started here — see `CHECKLIST.md` for exactly what is
blocked on which account or credential.
