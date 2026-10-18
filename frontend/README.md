# Psylink frontend

Next.js (App Router) + TypeScript strict, Tailwind v4, shadcn-style primitives, Recharts,
`@supabase/supabase-js`. There are **no Next.js API routes**: every read and write goes to the
FastAPI backend at `NEXT_PUBLIC_API_URL`, with the Supabase access token as a bearer token.

Progress is tracked in the root [`README.md`](../README.md#frontend-progress), not here.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local   # point it at a running backend and your Supabase project
npm run dev                  # http://localhost:3000
```

The backend must allow this origin: set `FRONTEND_ORIGIN=http://localhost:3000` in
`backend/.env`. Voice capture needs HTTPS (or localhost) — see the deploy notes in the root README.

## Environment

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL. All app data. |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project used for auth only. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable anon key. Never a service key. |
| `NEXT_PUBLIC_DEMO_PASSWORD` | Optional. Enables the demo buttons against the seeded demo accounts. |

## Known contract gaps

The backend does not serve everything the product spec asks for yet, and the client says so rather
than faking it:

- **`POST /demo/login {role}` does not exist.** The demo buttons fall back to a normal Supabase
  sign-in as the seeded demo account, which needs `NEXT_PUBLIC_DEMO_PASSWORD`. With neither
  available they report "Demo logins are not available in this deployment". The seeded auth users
  must also be created (`scripts/seed_demo.py --create-auth-users`) and their UUIDs must match the
  seeded `profiles.id`, or `/auth/me` answers 401.
- Alert acknowledgement is `POST /api/alerts/{id}/acknowledge`, not `PATCH /alerts/{id}`, because
  the backend's CORS list allows only GET/POST/DELETE/OPTIONS.
- Trends come from `GET /api/patients/{id}/trend` and carry mood, risk and summary only. Symptoms
  and emotions exist per check-in, so the small-multiple charts read up to 20 recent detail records
  instead of inventing a series.
- There is no account or bulk-data deletion endpoint. Settings can revoke consent and delete single
  check-ins; "delete everything" is disabled with an explanation.
- Errors arrive as `{"detail":{"code","message"}}`, plus bare-string auth details and FastAPI 422
  arrays. The client also reads the spec's `{"error":{...}}` shape, so either side can change.
- `src/lib/api.ts` holds one route table mapping each spec name to the path actually called.

## Commands

| Command | Does |
| --- | --- |
| `npm run lint` | ESLint (flat config, next/core-web-vitals + react-hooks) |
| `npm run typecheck` | `tsc --noEmit`, strict |
| `npm test` | Vitest unit/component tests |
| `npm run test:e2e` | Playwright smoke test (needs backend + seeded demo users) |
| `npm run build` | Production build |

## Layout

```
src/app/(auth)/       login, signup
src/app/(patient)/    home, consent, link, checkin, history, settings
src/app/(clinician)/  patients, patients/[id], checkins/[id], alerts
src/components/ui/    shadcn-style primitives (written locally, no registry install)
src/components/       auth, checkin, crisis, clinician, charts, states
src/lib/              api.ts (typed fetch), supabase.ts, auth/ (session provider, guards)
src/config/           crisis-resources.ts
src/types/api.ts      wire types, mirroring the backend's snake_case JSON
```

## Notes on the framework

Next 16 differs from older versions and `next.config.ts` runs with `cacheComponents`, so
`node_modules/next/dist/docs/` is the reference. Practical consequences here: all app data is
fetched in client components (`useEffect` + this API client) rather than in server components;
`error.tsx` must be a client component; browser-only APIs are touched inside effects and handlers,
never during render; and with cache components a route is **not** unmounted when you navigate away,
so anything with a lifecycle (the recorder, dialogs, forms) resets itself explicitly.

## Privacy rules baked into the code

Audio lives only in memory: no persistence, object URLs are revoked, MediaRecorder tracks are
stopped on every exit path. Transcripts are never logged. No analytics.
