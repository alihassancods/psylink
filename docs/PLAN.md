# Bridge — build plan

Last updated: 2026-10-18. Progress against this plan is tracked in [`CHECKLIST.md`](../CHECKLIST.md);
what the safety layer actually achieves is in [`eval-results.md`](eval-results.md).

## The problem

People living with a mental-health condition often go days between clinical contacts, and the
signal that matters — a slide into hopelessness — is invisible in that gap. Clinicians managing a
caseload cannot read every message. Bridge is a daily check-in that a patient can answer by
voice in thirty seconds, and a clinician-facing view that turns those answers into a ranked,
evidence-linked queue.

It is **not** a diagnostic tool and says so on every screen. It is a signal-carrying wire between
a patient who already has a clinician and the clinician who already has the patient.

## Architecture

```
Next.js (frontend, separate repo)
  ├── MediaRecorder → POST /api/transcribe → AssemblyAI (audio never stored)
  ├── editable transcript → POST /api/checkins
  └── clinician views ← GET /api/patients, /api/alerts

FastAPI backend (backend/)
  ├── analysis pipeline: keyword floor → ONE LLM call → guardrails → final_risk
  ├── Command Code Provider API (OpenAI-compatible) via the openai SDK
  └── Postgres + row-level security (Supabase) — the only authority on who sees what
```

Two external calls per check-in at most, and both are optional in the failure direction: no
AssemblyAI key means typing instead of talking; no model means `analysis_failed` with the
check-in still stored and risk defaulted to `moderate`.

## The load-bearing decisions

**Risk is a floor, not a vote.** A deterministic keyword screen runs before the model and outside
its reach. `final_risk` is the higher of the two. A model can raise risk; nothing a model says can
lower it. Clause-aware negation ("I'm **not** thinking of hurting myself") and idioms ("this exam
is **killing** me") keep the floor credible; risk-bearing double negatives ("I **don't** want to
live") are immune to suppression.

**Fail toward support.** If the model fails and the screen found nothing, the result is
`moderate` with `risk_source=fallback`, and crisis resources show. An unanalysable check-in is
never reported as calm, because "we could not tell" and "they are fine" must not look the same.

**Quotes must be verbatim.** `risk_evidence` is dropped unless it is an exact substring of the
transcript, and confidence falls to `low` when it is. A clinician reading an evidence quote knows
the patient said those words — that is the difference between a lead and a hallucination. The
screen is also run over the model's own quote, so a `low` classification that quotes "I want to
kill myself" is raised to `high`.

**Store before you think.** `POST /api/checkins` inserts the row as `pending` in its own committed
transaction, then analyses. A model outage, a garbled reply, or a failed status write leaves a
stored check-in, never a lost one.

**Authorisation lives in the database.** Clinician routes are plain reads through the caller's own
role; `app.has_active_consent` is what the policies are built from, so route code and the database
cannot drift apart. Revoking a consent closes history, not just future rows, with nothing to
invalidate. `analyses` is write-forbidden to `authenticated` — a patient cannot set their own risk
level, and neither can a request.

**Invite codes consume; they do not grant.** `app.redeem_invite` (SECURITY DEFINER) returns which
clinician a code belonged to; the consent row is still inserted through the patient's own RLS
policy. Knowing a code cannot produce access.

**Nothing patient-shaped is ever logged.** Sizes, counts, ids, and exception class names only.
This includes database errors, because SQLAlchemy writes bound parameters into its error text and
the bound parameter here is the patient's words.

**No audio on disk.** The AssemblyAI SDK accepts raw bytes, so there is no temp file; the remote
transcript is deleted on every path that obtained an id, including timeout and failure.

## Build order

1. Config and env surface, with fail-fast bounds on the numeric knobs.
2. Provider LLM client (JSON-mode probe, fallback model, truncation detection).
3. Keyword screen.
4. Schemas and prompt.
5. Pipeline and guardrails.
6. Check-ins endpoint (store-first), then consent, alerts, clinician views.
7. Speech-to-text client, then the transcribe endpoint.
8. Tests at every step; live checks behind `RUN_LIVE_TESTS=1`.
9. Safety evaluation, then the eval-in-CI gate.
10. Docs.

## Things learned the hard way (recorded so they are not repeated)

- **`max_tokens` on this provider caps reasoning tokens too.** At 800 the model intermittently
  returned *empty* content or half a JSON object. Mocked tests never caught it; the live smoke
  test did. Budget is 2048 with one retry at 4096, and `finish_reason="length"` is treated as a
  failure rather than partially trusted.
- **A negation window without clause boundaries is unsafe.** "I'm **not** sleeping **and** I want
  to kill myself" was suppressed by the "not" two clauses away. Negation now stops at punctuation
  and conjunctions.
- **Python's VERBOSE regex silently deletes literal spaces between words**, so `to live` compiled
  to `tolive` and never matched. Found by an offline evaluation, not by review.
- **`COMMENT ON POLICY` takes `name ON table`**, not a schema-qualified name.
- **The transaction-mode pooler (port 6543) rejects prepared statements.** The app works because
  `session.py` sets `statement_cache_size = 0`; alembic builds its own engine without it and fails
  on its very first query. Migrations against a hosted project go through the dashboard.
- **Deleting a parent row nulls its children's FK before you can query them.** Check-in delete
  removes the analysis first, or an orphaned summary of withdrawn words stays readable.

## Cut list, in order

The parts that may be dropped under time pressure, and the parts that may not.

| Cut first | Never cut |
| --- | --- |
| Safety evaluation script *(built and in CI — keep)* | Keyword floor that the model cannot lower |
| Rate limiting *(built — keep; it is in-process and per-worker)* | Fail-safe `moderate` on analysis failure |
| Email alerts *(keep the dashboard alert)* | Verbatim evidence check |
| History delete | AssemblyAI transcript deletion |
| Trends date filter | No transcripts, prompts, or responses in logs |

## Where the code lives

| Concern | Path |
| --- | --- |
| Risk floor | `backend/app/services/analysis/keywords.py` |
| Pipeline | `backend/app/services/analysis/pipeline.py` |
| Guardrails | `backend/app/services/analysis/guardrails.py` |
| Provider client | `backend/app/services/ai/llm_client.py` |
| Speech to text | `backend/app/services/stt/assemblyai_client.py` |
| Endpoints | `backend/app/api/` |
| Access rules | `backend/supabase/migrations/002_rls.sql`, `003_invites.sql` |
| Demo data | `backend/app/services/demo_seed.py`, `backend/scripts/seed_demo.py` |
| Evaluation | `backend/scripts/eval_safety.py`, `backend/scripts/safety_corpus.json` |
| Frontend | separate repo; its contract is in `backend/README.md` |
