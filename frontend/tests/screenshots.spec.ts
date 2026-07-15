/**
 * Capture submission screenshots.
 *
 * The brief's checklist asks for "Screenshots of the application". Generating
 * them from a real run — rather than cropping them by hand — means they cannot
 * drift from what the app actually renders.
 *
 * Run: npx playwright test tests/screenshots.spec.ts
 * Output: docs/screenshots/
 */
import { test, expect } from "@playwright/test";

const DIR = "../docs/screenshots";

test.describe.configure({ mode: "serial" });

/**
 * The app shell is `h-screen overflow-hidden` with the content scrolling inside
 * <main>, so the document never grows taller than the window and `fullPage` has
 * nothing extra to capture. Growing the viewport is what actually reveals the
 * whole page.
 */
async function tall(page: import("@playwright/test").Page, height: number) {
  await page.setViewportSize({ width: 1280, height });
}

test("01 dashboard", async ({ page }) => {
  await tall(page, 1000);
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("Dashboard");
  await page.waitForTimeout(600); // let the charts settle
  await page.screenshot({ path: `${DIR}/01-dashboard.png` });
});

test("02 new simulation form", async ({ page }) => {
  await tall(page, 1000);
  await page.goto("/simulation");
  await expect(page.locator("#weight")).toBeVisible();
  await page.waitForTimeout(400); // reference data populates the dropdowns
  await page.screenshot({ path: `${DIR}/02-new-simulation.png` });
});

test("03 results", async ({ page }) => {
  await tall(page, 2900);
  await page.goto("/simulation");
  await page.fill("#density", "0.35");
  await page.selectOption("#weight", "250");
  await page.fill("#qty", "100000");
  await page.locator("button[type='submit']").click();
  await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 40_000 });
  await expect(page.getByText("Product Volume")).toBeVisible();
  await expect(page.getByText(/Compared against/i)).toBeVisible();
  await page.waitForTimeout(1500); // recharts animation
  await page.screenshot({ path: `${DIR}/03-results.png` });
});

test("04 history", async ({ page }) => {
  await tall(page, 1000);
  await page.goto("/history");
  await expect(page.locator("h1")).toContainText("History");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${DIR}/04-history.png` });
});

test("05 compare", async ({ page }) => {
  await tall(page, 1200);
  await page.goto("/compare");
  await expect(page.locator("h1")).toContainText("Comparison");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${DIR}/05-compare.png` });
});

test("06 swagger", async ({ page }) => {
  await page.goto("http://127.0.0.1:8000/docs");
  await page.waitForSelector(".opblock", { timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${DIR}/06-swagger.png`, fullPage: true });
});

test("07 mobile responsive", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${DIR}/07-responsive-mobile.png`, fullPage: true });
});
