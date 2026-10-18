import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequireRole } from "@/lib/auth/require-role";
import { SessionProvider } from "@/lib/auth/session-provider";
import { createQueryClient } from "@/lib/query-client";
import { useConsentQuery } from "@/lib/queries";

/**
 * The bug these tests exist for: the route guard decided "this patient has no consent" from the
 * *default* value of a request that had not run yet, so every sign-in flashed /consent and — because
 * the guard's copy was never refreshed — kept bouncing people back there after they linked.
 *
 * A redirect may only follow a request that answered. Every test here controls whether
 * `/api/consent` has resolved and asserts what the guard does in that exact moment.
 */

const mocks = vi.hoisted(() => ({
  pathname: "/home",
  replace: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push, refresh: vi.fn() }),
  usePathname: () => mocks.pathname,
}));

vi.mock("@/lib/env", () => ({
  API_BASE_URL: "https://backend.test",
  DEMO_PASSWORD: "",
  SUPABASE_URL: "https://project.supabase.co",
  SUPABASE_ANON_KEY: "anon-key",
  SUPABASE_CONFIG_ERROR: null,
  isSupabaseConfigured: true,
}));

vi.mock("@/lib/supabase", () => ({
  getAccessToken: async () => "access-token",
  refreshAccessToken: async () => "fresh-token",
  clearSession: vi.fn(),
  getSupabaseClient: () => ({
    auth: {
      // Supabase reports the stored session as soon as you subscribe, which is what the provider
      // relies on for its first read.
      onAuthStateChange: (callback: (event: string, session: unknown) => void) => {
        queueMicrotask(() => callback("INITIAL_SESSION", { access_token: "access-token" }));
        return { data: { subscription: { unsubscribe: () => {} } } };
      },
      getSession: async () => ({ data: { session: { access_token: "access-token" } } }),
      signOut: vi.fn(),
    },
    from: () => ({ insert: async () => ({ error: null }) }),
  }),
}));

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (value: unknown) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (value: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

const asResponse = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  text: async () => JSON.stringify(body),
});

const PATIENT = { id: "patient-1", role: "patient", display_name: "Ada" };
const LINK = {
  consent_id: "c1",
  clinician_id: "clinician-1",
  clinician_name: "Dr Okonkwo",
  granted_at: "2026-10-01T09:00:00Z",
};

let consentGate: Deferred<ReturnType<typeof asResponse>>;
let fetchedPaths: string[];

beforeEach(() => {
  mocks.pathname = "/home";
  mocks.replace.mockReset();
  mocks.push.mockReset();
  consentGate = deferred();
  fetchedPaths = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      fetchedPaths.push(url);
      if (url.includes("/auth/me")) return asResponse(PATIENT);
      if (url.includes("/api/consent")) return consentGate.promise;
      return asResponse({}, 404);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The patient app screens, with the real provider, guard and cache in place. */
function renderGuarded(child?: React.ReactNode) {
  render(
    <Harness>
      <RequireRole role="patient" requireConsent>
        {child ?? <p>the app</p>}
      </RequireRole>
    </Harness>,
  );
}

function Harness({ children }: { children: React.ReactNode }) {
  const [client] = useState(createQueryClient);
  return (
    <QueryClientProvider client={client}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  );
}

describe("RequireRole consent gate", () => {
  it("does not send a patient to /consent while the consent check is still in flight", async () => {
    renderGuarded();

    // Identity resolves and the guard starts its link check, but that check has not answered.
    await waitFor(() => {
      expect(fetchedPaths.some((url) => url.includes("/api/consent"))).toBe(true);
    });
    expect(screen.getByText(/Checking your link/)).toBeInTheDocument();

    // This is the regression: the old default of "ready + hasConsent:false" satisfied the redirect
    // condition here, before a single byte came back.
    expect(mocks.replace).not.toHaveBeenCalledWith("/consent");

    consentGate.resolve(asResponse([LINK]));
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
    expect(mocks.replace).not.toHaveBeenCalledWith("/consent");
  });

  it("sends a patient to /consent when the check answers that they are not linked", async () => {
    renderGuarded();
    consentGate.resolve(asResponse([]));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/consent"));
  });

  it("lets a linked patient through with no redirect at all", async () => {
    renderGuarded();
    consentGate.resolve(asResponse([LINK]));
    await waitFor(() => expect(screen.getByText("the app")).toBeInTheDocument());
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("does not ask for the link list at all on /consent and /link", async () => {
    mocks.pathname = "/consent";
    renderGuarded();
    await waitFor(() => expect(fetchedPaths.some((url) => url.includes("/auth/me"))).toBe(true));
    // The exempt pages are how a patient gets a link, so the gate must not spend a request there.
    expect(fetchedPaths.some((url) => url.includes("/api/consent"))).toBe(false);
  });

  it("serves the guard and a screen from one request instead of two", async () => {
    // `/settings` used to fetch `/api/consent` twice — once in the guard, once in the view — and let
    // the two copies disagree about whether the person was still sharing.
    consentGate.resolve(asResponse([LINK]));
    renderGuarded(
      <>
        <p>the app</p>
        <ConsentConsumer />
      </>,
    );

    await waitFor(() => expect(screen.getByText("consent:1")).toBeInTheDocument());
    expect(fetchedPaths.filter((url) => url.includes("/api/consent"))).toHaveLength(1);
  });
});

function ConsentConsumer() {
  const consent = useConsentQuery(true);
  return <p>consent:{consent.data?.length ?? 0}</p>;
}
