# Psylink

**Your voice, between sessions.**

Psylink is a daily voice check-in for people living with a mental-health condition, paired with a dashboard that helps their psychologist or psychiatrist see how the week went before the next visit. A deterministic safety check sets a floor under the risk level that the language model can never lower.

> **Not a clinical instrument.** Psylink describes what a patient said. It does not assess, diagnose, or treat, and it is not emergency care. If you are in danger, contact local emergency services or a crisis line.

> **All demo data is synthetic.** Every check-in text, patient name, and evaluation example in this repository was invented for the demo. No real patient audio or text exists here.

**Live demo:** https://psylink.alihassancodes.com/

Use the **Try as patient** and **Try as psychologist** buttons. If the backend has been idle, the first request can take about a minute while the free host wakes up.

Built for **HealthHack 48**.

## The problem

A psychologist or psychiatrist might see a patient for an hour a week, or less. The rest of the time is invisible. Patients forget what happened and what they wanted to say, and providers have no early view of how things are going in between.

## What Psylink does

1. **Patients** record a short voice check-in, review and edit the transcript, and submit it.
2. **Analysis** turns the text into a summary, mood, emotions, symptom patterns, and a risk level, with the exact quote that supports any flag.
3. **Psychologists and psychiatrists** see a ranked patient list, trends over 7, 14, or 30 days, and the original transcript with the evidence quote highlighted.
4. **High-risk check-ins** send a “flagged for review” email alert. Patients see crisis resources right away when risk is moderate or high.

## How it works

```text
patient records ~30s of speech
   -> POST /api/transcribe   (AssemblyAI; audio never stored, transcript deleted after reading)
   -> patient edits the text and submits
   -> POST /api/checkins     (stored first, then analysed)
   -> keyword floor + ONE model call + guardrails  -> final risk
   -> provider is alerted, patient sees crisis resources if warranted
```

The keyword screen and the model run together, but they are not peers. **The keyword screen is a floor.** `final_risk` is the higher of the two, so the model can raise risk and can never lower it. If the model fails and the screen found nothing, the result is `moderate`, so “we could not tell” never looks the same as “they are fine”.

## What makes it safe

| Mechanism | Why it exists |
|---|---|
| Deterministic keyword floor | Survives any model behaviour, including prompt injection. Clause-aware negation and idiom handling keep it credible. |
| `moderate` fail-safe | A failed analysis degrades toward support, not toward silence. |
| Verbatim evidence quotes | A quote is kept only if it is an exact substring of what the patient said. Otherwise it is dropped and confidence is lowered. |
| Diagnostic-language blocklist | Summaries describe. A reply that names a condition is corrected once, then discarded. |
| Store before analysing | The check-in is saved before any model runs, so nothing a patient submits is lost. |
| Row-level security | Postgres decides visibility. Revoking consent closes history, not just future rows. |
| `analyses` unwritable by users | A patient or a request cannot set their own risk level. |
| No patient content in logs | Logs hold sizes, counts, ids, and exception class names only. |
| No audio on disk, remote transcript deleted | Uploads stay in memory, and the AssemblyAI transcript is deleted on every path that received an id, including timeouts. |

Measured, not asserted: **19 of 19 high-risk items in the evaluation corpus were reported `high`** by the full pipeline. Numbers and honest limitations are in [`docs/eval-results.md`](docs/eval-results.md).

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python, FastAPI, Alembic |
| Database and auth | Supabase (Postgres, Auth, row-level security) |
| Speech to text | AssemblyAI |
| Analysis | Command Code Provider API (OpenAI-compatible Chat Completions) via the `openai` SDK |
| Email alerts | Resend |
| Hosting | Vercel (frontend), Render (backend) |
| Tests and CI | pytest, GitHub Actions |

## Repository layout

```text
psylink/
  backend/        FastAPI service, migrations, seed script, tests
  frontend/       Next.js client (landing page, patient app, provider dashboard)
  docs/           PLAN.md (architecture and decisions), eval-results.md (safety evaluation)
  .github/        CI workflows
  CHECKLIST.md    Build and deployment progress
```

More detail:

| Topic | Where |
|---|---|
| Backend setup, endpoints, RLS, configuration | [`backend/README.md`](backend/README.md) |
| Frontend setup | [`frontend/README.md`](frontend/README.md) |
| Architecture and the decisions behind it | [`docs/PLAN.md`](docs/PLAN.md) |
| Safety evaluation and results | [`docs/eval-results.md`](docs/eval-results.md) |
| Build progress | [`CHECKLIST.md`](CHECKLIST.md) |

## Quick start

### Backend

```bash
cd backend
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run pytest -q                     # 406 passed, 3 skipped (live provider tests)
uv run python scripts/seed_demo.py   # 1 provider, 3 patients, 14 days of synthetic data
uv run fastapi dev app/main.py
```

Two external keys are needed for the full experience. Both are optional by design, and without them the app degrades instead of failing:

```bash
ASSEMBLYAI_API_KEY=...     # /api/transcribe returns 503 without it; typing still works
COMMANDCODE_API_KEY=...    # analysis fails safe to "moderate"; the check-in is still stored
```

The full configuration table is in [`backend/README.md`](backend/README.md#configuration).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # then fill in the values below
npm run dev
```

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend (no trailing slash) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon (public) key |

Never put a service-role key or any private key in the frontend.

## Deployment

**Backend (Render):** deploy from the `backend/` folder using its Dockerfile. Set Root Directory to `backend`, the health check path to `/health`, and add the environment variables listed in [`backend/README.md`](backend/README.md). Set `FRONTEND_ORIGIN` to the exact Vercel URL, including `https://` and with no trailing slash, to avoid CORS errors.

**Frontend (Vercel):** import the repo with Root Directory `frontend` and set the three variables above.

**Free-tier note:** Render's free web services sleep after about 15 minutes without traffic, so open `/health` a few minutes before a demo to wake the backend.

## Model provider

Analysis calls go to the [Command Code Provider API](https://commandcode.ai/docs/provider) through the official `openai` SDK. The default model is `deepseek/deepseek-v4-flash` and can be changed with `COMMANDCODE_MODEL` (verify IDs against `{base}/models`). One call per check-in produces the summary and the risk classification together.

One caveat found in live testing: on this provider, `max_tokens` also caps reasoning tokens, so a small budget can silently return empty or truncated JSON. The client detects both cases and retries once with a larger budget. See [`docs/PLAN.md`](docs/PLAN.md) under “Things learned the hard way”.

## Privacy

- Audio goes to AssemblyAI for transcription and is never stored by Psylink.
- Transcript text goes to the Command Code provider, and the model provider behind it, for analysis.
- Patients give explicit consent before any data is shared with a provider, and can revoke it at any time.
- Demo data is synthetic. Do not enter real personal or health information into the demo.

## Limitations

- Not clinically validated, and analysis can be wrong. That is why providers always see the original transcript and the supporting quote.
- Alerts are not real-time monitoring and are not a substitute for emergency help.
- Email delivery is not guaranteed or instant. The dashboard is the source of truth for alerts.
- Speech recognition can mishear, so patients can edit the transcript before submitting.

## Before production

This is a hackathon build. The full list is in [`backend/README.md`](backend/README.md#before-this-went-anywhere-near-production). In short:

1. Clinical review of the evaluation corpus and thresholds.
2. Region-aware crisis routing and a human escalation path with an SLA.
3. Distributed rate limiting and alert deduplication.
4. Data-processing agreements with both providers and a retention report.
5. An audit trail of who read which patient.
6. Penetration testing of the invite flow and the RLS matrix.
7. Jurisdiction-specific review of the consent text.

**Never cut:** consent, crisis card, “Need help now?” link, evidence highlight, demo buttons, and loading/error states.

## Disclaimer

Psylink is a hackathon prototype. It is not medical advice, not a medical device, and not emergency care.
