/**
 * The PDF export must capture the WHOLE report, not the first screen.
 *
 * The app shell is a 100vh flex row with overflow hidden — content scrolls
 * inside <main>, the document never grows, and without the print stylesheet's
 * shell-flattening the print engine clips at exactly one page. That shipped:
 * users got a one-page PDF of a six-page report. This test pins the fix by
 * generating a real PDF through the same Chromium print pipeline the browser's
 * dialog uses.
 *
 * Page counting: Chromium writes one uncompressed `/Type /Page` dict per page
 * (validated against pypdf on real output — both said 6). `[^s]` excludes the
 * `/Type /Pages` tree node.
 */
import { test, expect } from "@playwright/test";

test("print produces a multi-page report, not one clipped page", async ({
  page,
  request,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "page.pdf() is Chromium-only");

  const create = await request.post("http://localhost:8000/api/simulation", {
    data: {
      tea_density: 0.35,
      package_weight: 250,
      shipment_quantity: 100000,
      shipment_type: "total_weight",
      package_shape: "square",
      packaging_material: "paper",
    },
  });
  expect(create.status(), await create.text()).toBe(201);
  const { id } = await create.json();

  await page.goto(`/results/${id}`, { waitUntil: "networkidle" });
  await expect(page.getByText("Saving vs current practice").first()).toBeVisible({
    timeout: 30_000,
  });
  await page.waitForTimeout(1000);

  const pdf = await page.pdf({ format: "A4", printBackground: true });

  const pages = pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g)?.length ?? 0;
  expect(pages, "report must paginate past the first viewport").toBeGreaterThanOrEqual(3);
});
