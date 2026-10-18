import fs from "node:fs";
import path from "node:path";

import type { APIRequestContext } from "@playwright/test";

/** Shared e2e setup. These tests run against any deployment; the parts that need seeded demo data
 * say why they skipped rather than passing vacuously. */

export function readEnv(name: string): string {
  const fromProcess = process.env[name]?.trim();
  if (fromProcess) return fromProcess;
  const file = path.resolve(__dirname, "..", ".env.local");
  if (!fs.existsSync(file)) return "";
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
    if (match?.[1] === name) return match[2].replace(/^["']|["']$/g, "").trim();
  }
  return "";
}

export const API_URL = readEnv("NEXT_PUBLIC_API_URL") || "http://localhost:8000";
export const DEMO_PASSWORD = readEnv("NEXT_PUBLIC_DEMO_PASSWORD");

/**
 * Empty string means the demo walk can run. Non-empty is the reason it cannot, and is passed
 * straight to `test.skip` so a skipped test always says why rather than looking like a pass.
 */
export async function demoSkipReason(request: APIRequestContext): Promise<string> {
  try {
    const health = await request.fetch(`${API_URL}/health`, { timeout: 5_000 });
    if (!health.ok()) return `backend at ${API_URL} answered ${health.status()} on /health`;
  } catch {
    return `backend at ${API_URL} is not reachable`;
  }
  if (!DEMO_PASSWORD) {
    return "NEXT_PUBLIC_DEMO_PASSWORD is not set, so the demo buttons cannot sign into the seeded accounts";
  }
  return "";
}
