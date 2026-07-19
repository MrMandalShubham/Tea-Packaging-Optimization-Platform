/**
 * The journey that matters: run a real optimisation and check the result is
 * both correct and honestly presented.
 *
 * The existing smoke suite only asserts that pages render. A page can render
 * perfectly while the optimiser ships half-empty containers, so these tests
 * assert the business outcome instead.
 *
 * Requires: frontend on :3000, backend on :8000, database migrated.
 */
import { test, expect } from "@playwright/test";

test.describe("Optimisation journey", () => {
  test("runs a simulation and reports a usable result", async ({ page }) => {
    await page.goto("/simulation");

    await page.fill("#density", "0.35");
    await page.selectOption("#weight", "250");
    await page.fill("#qty", "100000");
    await page.locator("button[type='submit']").click();

    // The optimiser evaluates ~15k configurations; allow for a cold backend.
    await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 30_000 });
    await expect(page.locator("h1")).toContainText("Optimization Results");

    const body = await page.locator("body").innerText();

    // Every stage must have produced something.
    expect(body).toMatch(/\d+\s*×\s*\d+/); // dimensions rendered
    expect(body).toMatch(/40GP|40HC|20GP/); // a container was chosen
  });

  test("container utilisation is not embarrassing", async ({ page, request }) => {
    // Asserted through the API so the number is exact rather than scraped.
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
    expect(create.status()).toBe(201);
    const { id } = await create.json();

    const detail = await request.get(`http://localhost:8000/api/simulation/${id}`);
    const d = await detail.json();

    // The business problem in the brief is "low container utilisation".
    // The greedy pipeline this replaced scored 36.9% on exactly these inputs.
    expect(d.best_container.capacity_utilization_pct).toBeGreaterThan(60);
    expect(d.pallet.footprint_utilization_pct).toBeGreaterThan(75);
  });

  test("savings claim shows its basis", async ({ page }) => {
    await page.goto("/simulation");
    await page.fill("#density", "0.35");
    await page.selectOption("#weight", "250");
    await page.fill("#qty", "100000");
    await page.locator("button[type='submit']").click();
    await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 30_000 });

    // A savings number with no stated basis is unfalsifiable. The UI must say
    // what "Current" means.
    await expect(page.getByText(/Compared against/i)).toBeVisible();
    await expect(page.getByText(/same physics and the same rates/i)).toBeVisible();
  });

  test("every comparison row explains itself", async ({ page }) => {
    await page.goto("/simulation");
    await page.fill("#density", "0.35");
    await page.selectOption("#weight", "250");
    await page.fill("#qty", "100000");
    await page.locator("button[type='submit']").click();
    await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 30_000 });

    // The brief requires logic that is "transparent and explainable".
    await expect(page.getByText(/Custom-sized pouch/i)).toBeVisible();
    await expect(page.getByText(/Fewer containers on the same voyage/i)).toBeVisible();
  });

  test("all three container types are compared", async ({ request }) => {
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
    const { id } = await create.json();
    const d = await (await request.get(`http://localhost:8000/api/simulation/${id}`)).json();

    const types = [d.best_container, ...d.container_alternatives].map(
      (c: { container_type: string }) => c.container_type
    );
    expect(types.sort()).toEqual(["20GP", "40GP", "40HC"]);
  });
});

test.describe("Security", () => {
  test("no OpenAI key is exposed to the browser", async ({ page }) => {
    const openaiRequests: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("openai.com")) openaiRequests.push(r.url());
    });

    await page.goto("/simulation");
    await page.fill("#density", "0.35");
    await page.selectOption("#weight", "250");
    await page.fill("#qty", "1000");
    await page.locator("button[type='submit']").click();
    await page.waitForURL(/\/results\/[0-9a-f-]+/, { timeout: 30_000 });

    // Open the assistant — the old build called api.openai.com from here with the
    // key in an Authorization header.
    await page.getByRole("button", { name: /open ai assistant/i }).click();
    await expect(page.getByRole("dialog", { name: /ai assistant/i })).toBeVisible();

    expect(openaiRequests).toEqual([]);

    // And nothing key-shaped is reachable from client scripts.
    const leaked = await page.evaluate(() =>
      Object.keys((window as unknown as Record<string, unknown>) ?? {}).some((k) =>
        k.toLowerCase().includes("openai")
      )
    );
    expect(leaked).toBe(false);
  });
});

test.describe("Pallet type selection", () => {
  test("EUR1 pallet drives the whole plan, and the choice is visible", async ({
    page,
  }) => {
    await page.goto("/simulation");
    await page.fill("#density", "0.35");
    await page.selectOption("#weight", "250");
    await page.fill("#qty", "100000");
    await page.selectOption("#pallet", "eur1");
    await page.locator("button[type='submit']").click();

    await page.waitForURL(/\/results\/([0-9a-f-]+)/, { timeout: 30_000 });
    const id = page.url().match(/\/results\/([0-9a-f-]+)/)![1];

    // The chosen pallet is shown with the result, not silently swallowed.
    await expect(
      page.locator("text=EUR 1200×800").first()
    ).toBeVisible({ timeout: 15_000 });

    // And the recomputed layout actually rides the 1200×800 deck.
    const layout = await page.request.get(
      `http://localhost:8000/api/simulation/${id}/layout`
    );
    expect(layout.status()).toBe(200);
    const plan = await layout.json();
    expect(plan.pallet.length_mm).toBe(1200);
    expect(plan.pallet.width_mm).toBe(800);
  });
});
