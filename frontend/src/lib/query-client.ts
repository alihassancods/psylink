"use client";

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api";

/**
 * Client-side data cache. `use cache` / `cacheLife` are server-only in Next 16, so a route whose
 * data arrives from `useEffect` + `fetch` gets no framework caching at all — this is what the app
 * was missing, and the reason a guard and a page could disagree about the same endpoint.
 *
 * Tunables live in `src/lib/queries.ts` next to the keys they apply to.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        /**
         * Off on purpose: a clinician alt-tabbing back would otherwise re-pull the whole queue, and
         * a returning patient would re-pull their history, on every focus change.
         */
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
        gcTime: 10 * 60_000,
        retry: (attempt, error) => {
          // A 4xx is an answer, not a hiccup — retrying it only delays the screen that shows it.
          // Status 0 is the network-error sentinel from `api.ts`, which is worth one retry.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return attempt < 1;
        },
      },
      mutations: { retry: false },
    },
  });
}
