"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiError, api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { Alert, AuthMe, CheckinDetail, CheckinPage, ConsentLink, PatientPage, Trend } from "@/types/api";

/**
 * Every read in the app, in one place, with its cache lifetime beside it. Components ask for data
 * by name instead of hand-building a fetch in an effect, which is what let two copies of the same
 * endpoint disagree.
 *
 * What is cached is metadata about a person's day, never audio: transcripts are stored server-side
 * and only reach the browser when a screen asks for them (see README "Privacy rules baked into the
 * code"). Sign-out clears the whole cache — `session-provider.tsx`.
 */

const SECOND = 1_000;

/**
 * The one shape every data view already branches on — `loading`, `success`, or a friendly error with
 * a retry — kept from `use-api.ts` so the screens and their empty/error states stay untouched. The
 * transport underneath changed; the contract the UI was written against did not.
 */
export type QueryState<T> =
  | { status: "loading"; data: null; message: string; reload: () => void; isFetching: boolean }
  | { status: "success"; data: T; message: string; reload: () => void; isFetching: boolean }
  | { status: "error"; data: null; message: string; reload: () => void; isFetching: boolean };

export function asState<T>(query: {
  isPending: boolean;
  isError: boolean;
  isFetching?: boolean;
  data: T | undefined;
  error: unknown;
  refetch: () => Promise<unknown>;
}): QueryState<T> {
  const reload = () => {
    void query.refetch();
  };
  const isFetching = query.isFetching ?? false;
  if (query.isPending) {
    return { status: "loading", data: null, message: "", reload, isFetching: true };
  }
  if (query.isError) {
    return {
      status: "error",
      data: null,
      message:
        query.error instanceof ApiError
          ? query.error.message
          : "Something went wrong. Please try again.",
      reload,
      isFetching: false,
    };
  }
  return { status: "success", data: query.data as T, message: "", reload, isFetching };
}

export const STALE = {
  /** Identity. Only refetched when a Supabase auth event says it may have changed. */
  me: 30 * SECOND,
  /** Active clinician links. Changes only via redeem/revoke, both of which invalidate it. */
  consent: 60 * SECOND,
  checkins: 30 * SECOND,
  patients: 60 * SECOND,
  trend: 30 * SECOND,
  /** A stored check-in is immutable — it is committed before analysis and only ever deleted. */
  checkin: Infinity,
  alerts: 30 * SECOND,
} as const;

export function useMeQuery(enabled: boolean) {
  return useQuery<AuthMe>({
    queryKey: queryKeys.me,
    queryFn: () => api.me({ redirectOnUnauthenticated: false }),
    staleTime: STALE.me,
    enabled,
    // Bootstrap state, not a screen: an error here is a status the guard reads, not a retry button.
    retry: false,
  });
}

/**
 * `GET /api/consent` — the guard, the consent screen and the settings screen all read this one
 * query, so the answer cannot differ between them and it is fetched once per cache lifetime.
 *
 * `enabled` deliberately does NOT wait for `/auth/me`: both calls only need the access token, so
 * running them together removes one serial round trip from first paint. A clinician who lands on a
 * patient route may see a 403 here; the role check redirects them regardless, and the guard reads
 * `isSuccess` rather than the error.
 */
export function useConsentQuery(enabled: boolean) {
  return useQuery<ConsentLink[]>({
    queryKey: queryKeys.consent,
    queryFn: () => api.getConsentLinks(),
    staleTime: STALE.consent,
    enabled,
  });
}

/** Derived: an empty list means "not linked yet", which is also how the backend spells it. */
export function consentFrom(links: ConsentLink[] | undefined) {
  const newest = links?.[0];
  return {
    hasConsent: (links?.length ?? 0) > 0,
    links: links ?? [],
    clinicianName: newest?.clinician_name ?? null,
    grantedAt: newest?.granted_at ?? null,
  };
}

export function useCheckinsQuery(limit: number, offset = 0, enabled = true) {
  return useQuery<CheckinPage>({
    queryKey: queryKeys.checkins(limit, offset),
    queryFn: () => api.listCheckins({ limit, offset }),
    staleTime: STALE.checkins,
    enabled,
  });
}

export function usePatientsQuery(enabled = true) {
  return useQuery<PatientPage>({
    queryKey: queryKeys.patients,
    queryFn: () => api.listPatients(),
    staleTime: STALE.patients,
    enabled,
  });
}

export function useTrendQuery(patientId: string, days: 7 | 14 | 30) {
  return useQuery<Trend>({
    queryKey: queryKeys.trend(patientId, days),
    queryFn: () => api.getPatientTrends(patientId, days),
    staleTime: STALE.trend,
  });
}

/**
 * The symptom and emotion charts need per-check-in records, and each is its own cached query.
 * Changing the range therefore re-fetches only the trend: records already seen are read from
 * cache, and one slow or failed record degrades its own chart instead of blanking the page.
 */
export function useCheckinDetails(
  patientId: string,
  checkinIds: readonly string[],
): CheckinDetail[] {
  const queries = useMemo(
    () =>
      checkinIds.map((checkinId) => ({
        queryKey: queryKeys.checkin(patientId, checkinId),
        queryFn: () => api.getCheckinDetail(patientId, checkinId),
        staleTime: STALE.checkin,
        retry: 0,
      })),
    [patientId, checkinIds],
  );

  const results = useQueries({ queries });

  // Records arrive independently, so the charts draw from whatever has landed rather than waiting
  // for all twenty. A record that fails is simply absent, same as before.
  return useMemo(
    () => results.flatMap((result) => (result.data ? [result.data] : [])),
    [results],
  );
}

export function useCheckinDetailQuery(patientId: string, checkinId: string) {
  return useQuery<CheckinDetail>({
    queryKey: queryKeys.checkin(patientId, checkinId),
    queryFn: () => api.getCheckinDetail(patientId, checkinId),
    staleTime: STALE.checkin,
  });
}

export function useAlertsQuery(status: "open" | "all") {
  return useQuery<Alert[]>({
    queryKey: queryKeys.alerts(status),
    queryFn: () => api.listAlerts(status),
    staleTime: STALE.alerts,
  });
}
