import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, describeErrorBody, request, shouldTypeInstead } from "@/lib/api";

vi.mock("@/lib/supabase", () => ({
  getAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

import { getAccessToken, refreshAccessToken } from "@/lib/supabase";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.mocked(getAccessToken).mockResolvedValue("token-1");
  vi.mocked(refreshAccessToken).mockResolvedValue(null);
  Object.defineProperty(window, "location", {
    writable: true,
    value: { pathname: "/history", assign: vi.fn() },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("attaches the Supabase access token as a bearer token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, [{ consent_id: "c1" }]));

    await api.getConsentLinks();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/consent");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-1");
  });

  it("sends a JSON body with the right content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { consent_id: "c1" }));

    await api.redeemInvite("  AB12-cd34  ");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ code: "  AB12-cd34  " }));
  });

  it("never sets a content type for a multipart body, so the boundary is generated", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { transcript: "hello", duration_seconds: 12 }),
    );
    const form = new FormData();
    form.append("file", new Blob(["audio"], { type: "audio/webm" }), "check-in");

    await request("/api/transcribe", { method: "POST", body: form });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("Content-Type")).toBeNull();
    expect(init.body).toBe(form);
  });

  it("returns undefined for 204 instead of parsing an empty body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(api.deleteCheckin("checkin-1")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/checkins/checkin-1");
  });

  it("builds a query string and drops empty values", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { points: [] }));

    await api.getPatientTrends("patient-1", 30);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://localhost:8000/api/patients/patient-1/trend?days=30",
    );

    fetchMock.mockResolvedValue(jsonResponse(200, { items: [] }));
    await api.listCheckins({ limit: 20, offset: undefined });
    expect(fetchMock.mock.calls[1][0]).toBe("http://localhost:8000/api/checkins?limit=20");
  });

  describe("error parsing", () => {
    it("reads the spec shape {error:{code,message}}", async () => {
      fetchMock.mockResolvedValue(
        jsonResponse(400, { error: { code: "unsupported_audio", message: "Try typing instead." } }),
      );

      const error = await api
        .createCheckin({ transcript: "x" })
        .then(() => null)
        .catch((caught: unknown) => caught as ApiError);

      expect(error).toBeInstanceOf(ApiError);
      expect(error?.code).toBe("unsupported_audio");
      expect(error?.message).toBe("Try typing instead.");
      expect(error?.status).toBe(400);
    });

    it("reads the shape the backend emits {detail:{code,message}}", async () => {
      fetchMock.mockResolvedValue(
        jsonResponse(429, {
          detail: { code: "rate_limited", message: "Please wait 60 seconds." },
        }),
      );

      const error = await api.transcribe(new Blob()).catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("rate_limited");
      expect((error as ApiError).message).toBe("Please wait 60 seconds.");
    });

    it("reads a bare string detail from auth refusals", async () => {
      fetchMock.mockResolvedValue(jsonResponse(403, { detail: "requires role: clinician" }));

      const error = await api.listPatients().catch((caught: unknown) => caught);

      expect((error as ApiError).code).toBe("forbidden");
      expect((error as ApiError).message).toBe("requires role: clinician");
    });

    it("reads FastAPI 422 validation arrays", () => {
      expect(
        describeErrorBody(422, {
          detail: [{ type: "string_too_short", loc: ["body", "code"], msg: "String too short" }],
        }),
      ).toEqual({ code: "validation_error", message: "String too short" });
    });

    it("falls back to a safe message for an unparseable body", async () => {
      fetchMock.mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 }));

      const error = await api.listAlerts().catch((caught: unknown) => caught);

      expect((error as ApiError).code).toBe("http_502");
      expect((error as ApiError).message).toBe("The service did not respond in time.");
      expect((error as ApiError).message).not.toContain("Bad gateway");
    });

    it("maps a dropped connection to network_error", async () => {
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

      const error = await api.me().catch((caught: unknown) => caught);

      expect((error as ApiError).code).toBe("network_error");
      expect((error as ApiError).status).toBe(0);
    });
  });

  describe("401 handling", () => {
    it("refreshes once and retries with the new token", async () => {
      fetchMock
        .mockResolvedValueOnce(jsonResponse(401, { detail: "jwt expired" }))
        .mockResolvedValueOnce(jsonResponse(200, { id: "u1", role: "patient", display_name: null }));
      vi.mocked(refreshAccessToken).mockResolvedValue("token-2");

      await expect(api.me()).resolves.toMatchObject({ role: "patient" });

      expect(refreshAccessToken).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      const secondHeaders = new Headers(
        (fetchMock.mock.calls[1] as [string, RequestInit])[1].headers,
      );
      expect(secondHeaders.get("Authorization")).toBe("Bearer token-2");
    });

    it("redirects to /login when the refresh does not help", async () => {
      fetchMock.mockResolvedValue(jsonResponse(401, { detail: "missing bearer token" }));

      const error = await api.listCheckins().catch((caught: unknown) => caught);

      expect((error as ApiError).code).toBe("unauthenticated");
      expect(window.location.assign).toHaveBeenCalledWith("/login");
    });

    it("does not redirect for bootstrap calls, where 401 is an answer", async () => {
      fetchMock.mockResolvedValue(jsonResponse(401, { detail: "no profile for this user" }));

      await expect(api.me()).rejects.toThrow(ApiError);
      expect(window.location.assign).not.toHaveBeenCalled();
    });
  });

  describe("typed fallback decision", () => {
    it("switches to typing for transcribe refusals", () => {
      for (const [status, code] of [
        [400, "unsupported_audio"],
        [413, "audio_too_large"],
        [429, "rate_limited"],
        [503, "stt_unavailable"],
        [504, "stt_timeout"],
        [500, "internal_error"],
      ] as const) {
        expect(shouldTypeInstead(new ApiError(status, code, "x")), code).toBe(true);
      }
    });

    it("keeps consent and auth problems out of the typing fallback", () => {
      expect(shouldTypeInstead(new ApiError(403, "consent_required", "x"))).toBe(false);
      expect(shouldTypeInstead(new ApiError(401, "unauthenticated", "x"))).toBe(false);
      expect(shouldTypeInstead(new Error("boom"))).toBe(false);
    });
  });
});
