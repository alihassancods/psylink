import { API_BASE_URL } from "@/lib/env";
import { getAccessToken, refreshAccessToken } from "@/lib/supabase";
import type {
  AcknowledgedAlert,
  Alert,
  AuthMe,
  CheckinDetail,
  CheckinPage,
  CheckinResult,
  ConsentLink,
  InviteCreated,
  InviteRow,
  PatientPage,
  Trend,
  TranscribeResult,
} from "@/types/api";

/**
 * The single place the browser talks to FastAPI. There are no Next.js API routes: this client
 * attaches the Supabase access token, decodes the backend's refusal into an {@link ApiError},
 * refreshes once on 401, and sends the user to /login if the session really is gone.
 *
 * Route map. The product spec names a route, the deployed backend serves another; the client
 * calls what the backend actually answers to, and keeps the spec's method name so a rename on
 * either side is a one-line change here.
 *
 * | Spec                          | Backend called here        |
 * | ------------------------------| ---------------------------|
 * | POST /consent                 | POST /api/consent          |
 * | GET /consent/status           | GET /api/consent           |
 * | POST /link {invite_code}      | POST /api/consent {code}   |
 * | POST /transcribe              | POST /api/transcribe       |
 * | POST /checkins                | POST /api/checkins         |
 * | GET /checkins                 | GET /api/checkins          |
 * | DELETE /checkins/{id}         | DELETE /api/checkins/{id}  |
 * | GET /clinician/patients       | GET /api/patients          |
 * | GET /clinician/patients/{id}/trends | GET /api/patients/{id}/trend |
 * | GET /clinician/checkins/{id}  | GET /api/patients/{pid}/checkins/{cid} |
 * | GET /alerts                   | GET /api/alerts            |
 * | PATCH /alerts/{id}            | POST /api/alerts/{id}/acknowledge (CORS only allows GET/POST/DELETE) |
 * | POST /demo/login              | `src/lib/auth/session-provider.tsx` |
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

/** Backend limit on the approved text, so the UI can stop at the same place the API would. */
export const MAX_TEXT_CHARS = 20_000;

/**
 * Codes that mean "speech-to-text will not work on this attempt" — the check-in flow switches
 * to the typed fallback for any of them, and for 400/413/429/5xx generally.
 */
export const TYPE_INSTEAD_CODES = new Set([
  "unsupported_audio",
  "empty_audio",
  "audio_too_large",
  "audio_too_long",
  "rate_limited",
  "empty_transcript",
  "stt_timeout",
  "stt_unavailable",
  "stt_failed",
  "internal_error",
  "network_error",
]);

export function shouldTypeInstead(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (TYPE_INSTEAD_CODES.has(error.code)) return true;
  return error.status >= 400 && error.status < 600 && error.status !== 401 && error.status !== 403;
}

interface ErrorBody {
  code: string;
  message: string;
}

const GENERIC_MESSAGES: Record<number, string> = {
  400: "That request could not be processed.",
  403: "You do not have access to this.",
  404: "We could not find this.",
  413: "That recording is too large.",
  422: "Some of that was not valid.",
  429: "Too many attempts. Please wait a moment.",
  500: "Something went wrong. Please try again.",
  502: "The service did not respond in time.",
  503: "The service is unavailable right now.",
  504: "The service took too long to respond.",
};

/**
 * Accepts every refusal shape the backend produces: the spec's `{error:{code,message}}`, the
 * `{detail:{code,message}}` the API actually emits, FastAPI's bare-string auth `detail`, and
 * the 422 array of validation issues.
 */
export function describeErrorBody(status: number, body: unknown): ErrorBody {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;

    const error = record.error;
    if (error && typeof error === "object") {
      const { code, message } = error as Record<string, unknown>;
      if (typeof code === "string" || typeof message === "string") {
        return {
          code: typeof code === "string" ? code : `http_${status}`,
          message:
            typeof message === "string" && message
              ? message
              : (GENERIC_MESSAGES[status] ?? "Something went wrong."),
        };
      }
    }
    if (typeof error === "string" && error) {
      return { code: `http_${status}`, message: error };
    }

    const detail = record.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const { code, message } = detail as Record<string, unknown>;
      if (typeof code === "string" || typeof message === "string") {
        return {
          code: typeof code === "string" ? code : `http_${status}`,
          message:
            typeof message === "string" && message
              ? message
              : (GENERIC_MESSAGES[status] ?? "Something went wrong."),
        };
      }
    }
    if (typeof detail === "string" && detail) {
      // Auth and role refusals arrive as a bare sentence.
      const code = status === 401 ? "unauthenticated" : status === 403 ? "forbidden" : `http_${status}`;
      return { code, message: detail };
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as Record<string, unknown>;
      const message = typeof first?.msg === "string" ? first.msg : GENERIC_MESSAGES[status];
      return { code: "validation_error", message: message ?? "Some of that was not valid." };
    }
  }

  return {
    code: `http_${status}`,
    message: GENERIC_MESSAGES[status] ?? "Something went wrong.",
  };
}

function loginPath() {
  return "/login";
}

function goToLogin() {
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith(loginPath())) return;
  window.location.assign(loginPath());
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  /** JSON body. Mutually exclusive with `body`. */
  json?: unknown;
  /** Pre-built body: a Blob (raw audio) or FormData (multipart audio). */
  body?: BodyInit | null;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** False for bootstrap calls, where a 401 is an expected answer, not a session loss. */
  redirectOnUnauthenticated?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const url = new URL(`${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/**
 * One request, one token, one refresh attempt. Non-JSON responses (204) come back as undefined,
 * because `DELETE /api/checkins/{id}` legitimately has no body.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    json,
    body,
    query,
    signal,
    redirectOnUnauthenticated = true,
  } = options;

  const execute = async (token: string | null): Promise<Response> => {
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (json !== undefined) headers.set("Content-Type", "application/json");
    // A Blob/FormData body must NOT get a hand-written Content-Type: the boundary is generated.

    try {
      return await fetch(buildUrl(path, query), {
        method,
        headers,
        body: json !== undefined ? JSON.stringify(json) : (body ?? null),
        signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "network_error", "We could not reach Psylink. Check your connection.");
    }
  };

  let token = await getAccessToken();
  let response = await execute(token);

  if (response.status === 401) {
    const refreshed = await refreshAccessToken().catch(() => null);
    if (refreshed && refreshed !== token) {
      token = refreshed;
      response = await execute(token);
    }
  }

  if (response.status === 401) {
    if (redirectOnUnauthenticated) goToLogin();
    const body = await parseBody(response);
    const { message } = describeErrorBody(401, body);
    throw new ApiError(401, "unauthenticated", message, body);
  }

  const parsed = await parseBody(response);

  if (!response.ok) {
    const { code, message } = describeErrorBody(response.status, parsed ?? null);
    throw new ApiError(response.status, code, message, parsed);
  }

  return parsed as T;
}

export const api = {
  /** Authoritative identity: the role comes from the backend's profile row, never a JWT claim. */
  me: (options: { redirectOnUnauthenticated?: boolean } = {}) =>
    request<AuthMe>("/auth/me", { redirectOnUnauthenticated: options.redirectOnUnauthenticated ?? false }),

  /** Active clinician links. Empty array means "not linked yet". */
  getConsentLinks: () => request<ConsentLink[]>("/api/consent"),

  /** Redeems a clinician invite code, which is how consent is granted here. */
  redeemInvite: (inviteCode: string) =>
    request<ConsentLink>("/api/consent", { method: "POST", json: { code: inviteCode } }),

  revokeConsent: (clinicianId: string) =>
    request<undefined>(`/api/consent/${clinicianId}`, { method: "DELETE" }),

  /** Clinician creates a single-use invite; the plaintext code is only in this response. */
  createInvite: () => request<InviteCreated>("/api/link", { method: "POST" }),

  listInvites: () => request<InviteRow[]>("/api/link"),

  transcribe: (audio: Blob) => {
    const form = new FormData();
    form.append("file", audio, "check-in");
    return request<TranscribeResult>("/api/transcribe", { method: "POST", body: form });
  },

  createCheckin: (input: { transcript?: string; note?: string; duration_seconds?: number }) =>
    request<CheckinResult>("/api/checkins", { method: "POST", json: input }),

  listCheckins: (params: { limit?: number; offset?: number } = {}) =>
    request<CheckinPage>("/api/checkins", { query: params }),

  deleteCheckin: (checkinId: string) =>
    request<undefined>(`/api/checkins/${checkinId}`, { method: "DELETE" }),

  listPatients: (limit = 100) =>
    request<PatientPage>("/api/patients", { query: { limit } }),

  getPatientTrends: (patientId: string, days: 7 | 14 | 30) =>
    request<Trend>(`/api/patients/${patientId}/trend`, { query: { days } }),

  getCheckinDetail: (patientId: string, checkinId: string) =>
    request<CheckinDetail>(`/api/patients/${patientId}/checkins/${checkinId}`),

  listAlerts: (status: "open" | "all" = "open", limit = 50) =>
    request<Alert[]>("/api/alerts", { query: { status, limit } }),

  /** Not idempotent: a second acknowledgement is a 404, so callers disable while pending. */
  acknowledgeAlert: (alertId: string) =>
    request<AcknowledgedAlert>(`/api/alerts/${alertId}/acknowledge`, { method: "POST" }),
};
