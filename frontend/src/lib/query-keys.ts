/**
 * Cache keys for every read the app makes. Kept in a hook-free module so mutation handlers and the
 * session provider can invalidate without importing client hooks.
 *
 * A key must encode everything that changes the answer — that is what makes "switched the range,
 * so refetch the whole world" impossible.
 */
export const queryKeys = {
  me: ["me"] as const,
  consent: ["consent"] as const,
  checkins: (limit: number, offset: number) => ["checkins", limit, offset] as const,
  patients: ["patients"] as const,
  trend: (patientId: string, days: number) => ["trend", patientId, days] as const,
  checkin: (patientId: string, checkinId: string) => ["checkin", patientId, checkinId] as const,
  alerts: (status: "open" | "all") => ["alerts", status] as const,
};
