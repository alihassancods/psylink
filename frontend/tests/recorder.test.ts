import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MAX_RECORD_SECONDS,
  formatClock,
  isMediaRecorderSupported,
  isMicrophoneBlocked,
  microphoneErrorMessage,
  pickMimeType,
} from "@/lib/recorder";

function stubRecorder(supportedTypes: string[]) {
  vi.stubGlobal("MediaRecorder", {
    isTypeSupported: (type: string) => supportedTypes.includes(type),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("recorder capability", () => {
  it("caps a recording at the backend's limit", () => {
    expect(MAX_RECORD_SECONDS).toBe(120);
  });

  it("prefers webm/opus, which Chrome and Firefox both give us", () => {
    stubRecorder(["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]);
    expect(pickMimeType()).toBe("audio/webm;codecs=opus");
  });

  it("falls back to mp4 when the browser only offers that", () => {
    stubRecorder(["audio/mp4"]);
    expect(pickMimeType()).toBe("audio/mp4");
  });

  it("returns null rather than a type the backend would reject", () => {
    stubRecorder(["audio/x-matroska"]);
    expect(pickMimeType()).toBeNull();
  });

  it("says recording is unavailable when the browser has no MediaRecorder", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    expect(isMediaRecorderSupported()).toBe(false);
  });

  it("says recording is available with MediaRecorder and getUserMedia", () => {
    vi.stubGlobal("MediaRecorder", function MediaRecorder() {});
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: () => Promise.resolve({}) },
    });
    expect(isMediaRecorderSupported()).toBe(true);
  });
});

describe("microphone failures", () => {
  it("recognises a blocked permission and points at typing", () => {
    const error = { name: "NotAllowedError" };
    expect(isMicrophoneBlocked(error)).toBe(true);
    expect(microphoneErrorMessage(error)).toContain("type your check-in instead");
  });

  it("recognises a missing microphone", () => {
    expect(isMicrophoneBlocked({ name: "NotFoundError" })).toBe(false);
    expect(microphoneErrorMessage({ name: "NotFoundError" })).toContain("No microphone");
  });

  it("keeps an unknown failure calm and useful", () => {
    expect(microphoneErrorMessage({ name: "WhateverError" })).toContain("Try again");
  });
});

describe("timer text", () => {
  it("formats minutes and seconds", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65)).toBe("1:05");
    expect(formatClock(MAX_RECORD_SECONDS)).toBe("2:00");
  });

  it("never shows a negative clock", () => {
    expect(formatClock(-3)).toBe("0:00");
  });
});
