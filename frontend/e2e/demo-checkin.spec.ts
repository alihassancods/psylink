import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * Demo smoke test. The guard tests run against any deployment. The full patient→clinician walk
 * needs the seeded backend (`scripts/seed_demo.py --create-auth-users`) and
 * `NEXT_PUBLIC_DEMO_PASSWORD`; without them it is skipped with the reason, never faked.
 */

function readEnv(name: string): string {
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

const API_URL = readEnv("NEXT_PUBLIC_API_URL") || "http://localhost:8000";
const DEMO_PASSWORD = readEnv("NEXT_PUBLIC_DEMO_PASSWORD");

/** Non-empty = reason the demo walk cannot run here. */
let demoUnavailable = "";

test.beforeAll(async ({ request }) => {
  try {
    const health = await request.fetch(`${API_URL}/health`, { timeout: 5_000 });
    if (!health.ok()) {
      demoUnavailable = `backend at ${API_URL} answered ${health.status()} on /health`;
      return;
    }
  } catch {
    demoUnavailable = `backend at ${API_URL} is not reachable`;
    return;
  }
  if (!DEMO_PASSWORD) {
    demoUnavailable =
      "NEXT_PUBLIC_DEMO_PASSWORD is not set, so the demo buttons cannot sign into the seeded accounts";
  }
});

async function demoSignIn(page: Page, button: string, landing: RegExp) {
  await page.goto("/login");
  await page.getByRole("button", { name: button }).click();
  await page.waitForURL(landing, { timeout: 15_000 });
}

test.describe("access guards", () => {
  test("anonymous visitors are routed to the login screen", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("button", { name: "Try as demo patient" })).toBeVisible();
    await expect(
      page.getByText("Demo accounts hold synthetic data only"),
    ).toBeVisible();

    for (const route of ["/home", "/checkin", "/history", "/settings", "/patients", "/alerts"]) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
    }
  });
});

test.describe("demo walk", () => {
  test("a typed patient check-in reaches the clinician detail screen", async ({ page }) => {
    if (demoUnavailable) test.skip(true, `demo walk skipped: ${demoUnavailable}`);

    const note = `Psylink smoke note ${Date.now()}. I slept badly but the day was manageable.`;

    await demoSignIn(page, "Try as demo patient", /\/home|\/consent|\/link/);
    if (!/\/home/.test(page.url())) {
      throw new Error(
        "seeded demo patient arrived at the consent/link step — re-run scripts/seed_demo.py",
      );
    }

    // Force the typed fallback deterministically: with no MediaRecorder the recorder offers
    // "Type instead" immediately, so the walk never depends on headless mic permissions.
    // Registered before the fresh navigation below, which is what re-runs init scripts.
    await page.addInitScript(() => {
      delete (window as unknown as { MediaRecorder?: unknown }).MediaRecorder;
    });
    await page.goto("/checkin");
    await page.getByRole("button", { name: "Type instead" }).click();
    const box = page.getByLabel("Your words");
    await expect(box).toBeVisible({ timeout: 10_000 });
    await box.fill(note);
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(page.getByRole("heading", { name: "Thank you for checking in" })).toBeVisible({
      timeout: 30_000,
    });

    // Remember who we were so the clinician can find the same person.
    const greeting = await page
      .getByText(/Hello, .+\. Only your psychologist/)
      .first()
      .textContent();
    const displayName = /Hello, (.+?)\./.exec(greeting ?? "")?.[1];
    expect(displayName, "patient display name visible on home").toBeTruthy();

    await page.getByRole("button", { name: "Done" }).click();
    await expect(page).toHaveURL(/\/home/);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });

    await demoSignIn(page, "Try as demo psychologist", /\/patients/);
    await page.getByRole("link", { name: displayName! }).first().click();
    await expect(page).toHaveURL(/\/patients\/[^/]+$/);

    const firstOpen = page.getByRole("link", { name: "Open check-in" }).first();
    await expect(firstOpen).toBeVisible({ timeout: 15_000 });
    await firstOpen.click();

    // The detail screen carries the verbatim transcript — the strongest proof the row survived.
    await expect(page.getByText(note).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/AI-generated/i).first()).toBeVisible();
  });

  test("alerts list renders for a clinician without throwing", async ({ page }) => {
    if (demoUnavailable) test.skip(true, `demo walk skipped: ${demoUnavailable}`);
    await demoSignIn(page, "Try as demo psychologist", /\/patients/);
    await page.goto("/alerts");
    await expect(page.getByRole("heading", { name: "Alerts" })).toBeVisible();
    await expect(
      page.getByText("Alerts are raised for high-risk check-ins only.").or(
        page.getByRole("button", { name: "Acknowledge" }).first(),
      ),
    ).toBeVisible({ timeout: 15_000 });
  });
});
