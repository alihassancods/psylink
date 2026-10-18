import { expect, test } from "@playwright/test";

import { demoSkipReason } from "./helpers";

/**
 * Landing page checks that only a browser can answer: does it fit 360px, is every target big
 * enough for a thumb, can the page be used without a mouse, and does the heading outline stay
 * sane. Run against the built output, not the dev server, so what is measured is what ships.
 */

const MOBILE = { width: 360, height: 740 };

test.describe("landing page", () => {
  test("fits 360px with no horizontal overflow", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/");

    const overflow = await page.evaluate(() => {
      const doc = document.scrollingElement ?? document.documentElement;
      const wide = Array.from(document.querySelectorAll<HTMLElement>("body *"))
        .filter((el) => {
          const style = getComputedStyle(el);
          if (style.position === "fixed" || style.position === "absolute") return false;
          return el.getBoundingClientRect().right > window.innerWidth + 1;
        })
        .slice(0, 5)
        .map((el) => `${el.tagName.toLowerCase()}.${el.className.toString().split(" ")[0]}`);
      return { scrollWidth: doc.scrollWidth, innerWidth: window.innerWidth, wide };
    });

    expect(overflow.scrollWidth, `elements past the edge: ${overflow.wide.join(", ")}`).toBeLessThanOrEqual(
      overflow.innerWidth + 1,
    );
  });

  test("every tap target is at least 44px", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/");

    const tooSmall = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>("a[href], button"))
        // The skip link is visually hidden until focused, so it has no box to measure.
        .filter((el) => !el.classList.contains("sr-only"))
        .filter((el) => el.offsetParent !== null || getComputedStyle(el).position === "sticky")
        .map((el) => {
          const box = el.getBoundingClientRect();
          return { label: (el.textContent ?? el.getAttribute("aria-label") ?? "?").trim().slice(0, 40), h: box.height, w: box.width };
        })
        .filter((item) => item.h > 0 && (item.h < 44 || item.w < 44)),
    );

    expect(tooSmall, JSON.stringify(tooSmall)).toEqual([]);
  });

  test("one h1, and heading levels never skip a rank", async ({ page }) => {
    await page.goto("/");

    const levels = await page.$$eval("h1, h2, h3, h4, h5, h6", (nodes) =>
      nodes.map((node) => Number(node.tagName.slice(1))),
    );

    expect(levels.filter((level) => level === 1)).toHaveLength(1);
    let previous = 1;
    for (const level of levels) {
      expect(level, `heading jump from h${previous} to h${level}`).toBeLessThanOrEqual(previous + 1);
      previous = level;
    }
  });

  test("the skip link is the first stop and points at the main region", async ({ page }) => {
    await page.goto("/");

    await page.keyboard.press("Tab");
    const skip = page.locator("a[href='#main']");
    await expect(skip).toBeVisible();
    await expect(skip).toBeFocused();

    const mainCount = await page.locator("main").count();
    expect(mainCount, "nested main landmarks").toBe(1);
  });

  test("the FAQ opens from the keyboard alone", async ({ page }) => {
    await page.goto("/");

    const question = page.getByText("Does Psylink replace therapy?");
    await question.scrollIntoViewIfNeeded();
    await question.focus();
    await expect(question).toBeFocused();

    const details = page.locator("details", { has: question });
    await expect(details).not.toHaveAttribute("open", "");
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("open", "");
    await expect(page.getByText(/It supports the care you already have/)).toBeVisible();
  });

  test("every in-page nav link resolves to a real section", async ({ page }) => {
    await page.goto("/");

    for (const href of ["#how", "#safety", "#faq", "#demo"]) {
      await expect(page.locator(`section${href}`)).toHaveCount(1);
    }
  });

  test("every section is fully visible without scrolling", async ({ page }) => {
    // Guards against a scroll-linked fade: an element waiting at the first frame of such an
    // animation is opacity 0, so a full-page capture, a print, or a crawler that does not scroll
    // would see empty space where the copy should be.
    await page.goto("/");

    const faded = await page.evaluate(() =>
      Array.from(document.querySelectorAll("section"))
        .map((section) => ({
          label: section.id ?? section.getAttribute("aria-label") ?? "section",
          opacity: Number(getComputedStyle(section).opacity),
        }))
        .filter((entry) => entry.opacity < 0.99),
    );

    expect(faded, JSON.stringify(faded)).toEqual([]);
  });

  test("stays public for a signed-out visitor", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Not emergency care. Demo data is synthetic.")).toBeVisible();
  });

  test("shows the social preview tags a judge will actually see when the link is shared", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", /Psylink/);
    // The generated image URL is content-hashed without a file extension, so the declared type is
    // what a crawler can read — the bytes themselves are checked in the next test.
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
      "content",
      /opengraph-image/,
    );
    await expect(page.locator('meta[property="og:image:type"]')).toHaveAttribute(
      "content",
      "image/png",
    );
    await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute(
      "content",
      /Not emergency care/,
    );
  });

  test("the OG image renders at 1200x630", async ({ request }) => {
    const html = await (await request.get("/")).text();
    const match = /property="og:image" content="([^"]+)"/.exec(html);
    expect(match, "no og:image found").not.toBeNull();

    const url = new URL(match![1]);
    const response = await request.get(`${url.pathname}${url.search}`);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBe("image/png");

    const body = await response.body();
    // IHDR width/height are big-endian ints at byte 16.
    expect(body.readUInt32BE(16)).toBe(1200);
    expect(body.readUInt32BE(20)).toBe(630);
  });

  test("Try as patient reaches /home", async ({ page, request }) => {
    const reason = await demoSkipReason(request);
    test.skip(!!reason, `demo walk skipped: ${reason}`);

    await page.goto("/");
    // The page carries the pair twice on purpose — hero and closing CTA — so scope, don't guess.
    await page.getByRole("button", { name: "Try as patient" }).first().click();
    // A cold free-tier backend can take most of a minute, which is why the button says so.
    await expect(page).toHaveURL(/\/home/, { timeout: 90_000 });
  });

  test("the closing CTA reaches the patient queue", async ({ page, request }) => {
    const reason = await demoSkipReason(request);
    test.skip(!!reason, `demo walk skipped: ${reason}`);

    await page.goto("/");
    await page
      .locator("#demo")
      .getByRole("button", { name: "Try as psychologist" })
      .click();
    await expect(page).toHaveURL(/\/patients/, { timeout: 90_000 });
  });
});
