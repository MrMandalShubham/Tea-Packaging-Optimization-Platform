/**
 * Capture the 3D container load view.
 *
 * Split from screenshots.spec.ts because WebGL needs a real GPU-ish context and a
 * moment to settle; keeping it separate stops a slow render from flaking the rest
 * of the screenshot suite.
 */
import { test, expect } from "@playwright/test";

const DIR = "../docs/screenshots";

test("08 3D container load", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.goto("/simulation");
  await page.fill("#density", "0.35");
  await page.selectOption("#weight", "250");
  await page.fill("#qty", "100000");
  await page.locator("button[type='submit']").click();
  await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 40_000 });

  // The scene is behind a click: three.js is ~600 KB and is not fetched until
  // someone actually wants it.
  await page.getByRole("button", { name: /load 3d view/i }).click();

  const canvas = page.locator("[data-testid='container-3d'] canvas");
  await expect(canvas).toBeVisible({ timeout: 30_000 });

  // The overlay proves the scene is driven by the real plan, not placeholder art.
  await expect(page.getByText(/cartons ·/)).toBeVisible();

  await page.locator("[data-testid='container-3d']").scrollIntoViewIfNeeded();
  await page.waitForTimeout(2500); // let WebGL draw

  await page.locator("[data-testid='container-3d']").screenshot({
    path: `${DIR}/08-3d-container.png`,
  });
});
