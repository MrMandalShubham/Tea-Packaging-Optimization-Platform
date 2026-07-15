/**
 * E2E smoke tests for Tea Packaging Optimization UI.
 *
 * Run: npx playwright test
 * Requires: frontend running on localhost:3000, backend on localhost:8000
 */
import { test, expect } from "@playwright/test";

test.describe("Page Navigation", () => {
  test("dashboard loads", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("Dashboard");
  });

  test("new simulation page loads", async ({ page }) => {
    await page.goto("/simulation");
    await expect(page.locator("h1")).toContainText("New Simulation");
    await expect(page.locator("#density")).toBeVisible();
    await expect(page.locator("#weight")).toBeVisible();
    await expect(page.locator("#qty")).toBeVisible();
  });

  test("compare page loads", async ({ page }) => {
    await page.goto("/compare");
    await expect(page.locator("h1")).toContainText("Comparison");
  });

  test("history page loads", async ({ page }) => {
    await page.goto("/history");
    await expect(page.locator("h1")).toContainText("History");
  });

  test("sidebar navigation works", async ({ page }) => {
    await page.goto("/");
    // Click "New Simulation" in sidebar
    await page.locator("aside a").filter({ hasText: "New Simulation" }).click();
    await expect(page.locator("h1")).toContainText("New Simulation");

    // Click "History"
    await page.locator("aside a").filter({ hasText: "History" }).click();
    await expect(page.locator("h1")).toContainText("History");
  });
});

test.describe("Form Validation", () => {
  test("new simulation form has all inputs", async ({ page }) => {
    await page.goto("/simulation");
    const inputs = ["#density", "#weight", "#qty", "#shape", "#material"];
    for (const id of inputs) {
      await expect(page.locator(id)).toBeVisible();
    }
  });

  test("submit with empty fields shows HTML5 validation", async ({ page }) => {
    await page.goto("/simulation");
    // Clear default values
    await page.fill("#density", "");
    await page.fill("#weight", "");
    await page.fill("#qty", "");
    // Click submit
    await page.locator("button[type='submit']").click();
    // Should show validation (form won't submit)
    await expect(page.locator("#density:invalid")).toBeVisible();
  });
});

test.describe("Responsive Design", () => {
  test("hamburger menu appears on mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 }); // iPhone
    await page.goto("/");
    // Should see hamburger button
    await expect(page.locator("button svg.lucide-menu")).toBeVisible();
  });
});
