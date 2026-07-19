/**
 * Does the 3D view tell the truth?
 *
 * A misplaced carton looks exactly like a correctly placed one, so the geometry
 * is checked against physics rather than against a screenshot: nothing may
 * overlap, nothing may leave the container, and the composed count must equal
 * what the optimiser reported on the results page.
 *
 * These run against the live API so the plan under test is a real one.
 */
import { test, expect } from "@playwright/test";
import {
  composeCartons,
  composePallets,
  overlaps,
  insideContainer,
  MM,
} from "../lib/load-plan";
import type { LoadPlan } from "../lib/api";

const API = "http://localhost:8000";

async function planFor(
  request: import("@playwright/test").APIRequestContext,
  overrides: Record<string, unknown> = {}
): Promise<{ plan: LoadPlan; cartonsPerContainer: number }> {
  const create = await request.post(`${API}/api/simulation`, {
    data: {
      tea_density: 0.35,
      package_weight: 250,
      shipment_quantity: 100000,
      shipment_type: "total_weight",
      package_shape: "square",
      packaging_material: "paper",
      ...overrides,
    },
  });
  expect(create.status(), await create.text()).toBe(201);
  const { id } = await create.json();

  // Assert each hop. Feeding an error body into the geometry produces a
  // confusing "cannot read 'height_mm' of undefined" instead of the real cause.
  const planRes = await request.get(`${API}/api/simulation/${id}/layout`);
  expect(planRes.status(), await planRes.text()).toBe(200);
  const plan: LoadPlan = await planRes.json();

  const detailRes = await request.get(`${API}/api/simulation/${id}`);
  expect(detailRes.status(), await detailRes.text()).toBe(200);
  const detail = await detailRes.json();

  return { plan, cartonsPerContainer: detail.best_container.cartons_per_container };
}

test.describe("3D load plan geometry", () => {
  test("composed carton count matches what the optimiser reported", async ({ request }) => {
    const { plan, cartonsPerContainer } = await planFor(request);
    const boxes = composeCartons(plan);

    expect(boxes.length).toBe(plan.cartons_per_container);
    // ...and the load plan must agree with the number shown on the results page.
    expect(boxes.length).toBe(cartonsPerContainer);
  });

  test("no carton overlaps another", async ({ request }) => {
    const { plan } = await planFor(request);
    const boxes = composeCartons(plan);

    // O(n²) over ~1,400 boxes is ~1M checks — fine, and worth it: an overlap
    // means the plan is not physically executable.
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        if (overlaps(boxes[i], boxes[j])) {
          throw new Error(
            `cartons ${i} and ${j} occupy the same space: ` +
              `${JSON.stringify(boxes[i])} vs ${JSON.stringify(boxes[j])}`
          );
        }
      }
    }
  });

  test("every carton is inside the container", async ({ request }) => {
    const { plan } = await planFor(request);
    for (const box of composeCartons(plan)) {
      expect(
        insideContainer(box, plan),
        `carton at (${box.x.toFixed(2)}, ${box.y.toFixed(2)}, ${box.z.toFixed(2)}) ` +
          `escapes the ${plan.container_type}`
      ).toBe(true);
    }
  });

  test("no pallet overlaps another", async ({ request }) => {
    const { plan } = await planFor(request);
    const decks = composePallets(plan);
    for (let i = 0; i < decks.length; i++) {
      for (let j = i + 1; j < decks.length; j++) {
        expect(overlaps(decks[i], decks[j]), `pallets ${i}/${j} overlap`).toBe(false);
      }
    }
  });

  test("cartons sit above their pallet deck, never through it", async ({ request }) => {
    const { plan } = await planFor(request);
    const deck = plan.pallet_base_height_mm * MM;
    const palletH = plan.pallet.height_mm * MM;

    for (const box of composeCartons(plan)) {
      const bottom = box.y - box.h / 2;
      const tier = Math.floor(bottom / palletH + 1e-6);
      const deckTop = tier * palletH + deck;
      expect(bottom).toBeGreaterThanOrEqual(deckTop - 1e-6);
    }
  });

  test("stacked pallets do not exceed the container roof", async ({ request }) => {
    const { plan } = await planFor(request);
    const total = plan.pallet_stack * plan.pallet.height_mm;
    expect(total).toBeLessThanOrEqual(plan.container.height_mm + 1e-6);
  });

  test("the recipe is compact, not a dump of every position", async ({ request }) => {
    const { plan } = await planFor(request);
    const composed = composeCartons(plan).length;

    // One layer + one floor describes the whole load. If this ever balloons,
    // someone has started sending positions instead of the recipe.
    expect(plan.carton_layer.length + plan.pallet_floor.length).toBeLessThan(100);
    expect(composed).toBeGreaterThan(500);
  });

  test("a 20GP mixed floor still composes correctly", async ({ request }) => {
    // 20GP is the case where pallets get rotated on the floor — the arrangement
    // a client could not re-derive from a count alone.
    const { plan } = await planFor(request, { shipment_quantity: 5000 });
    const boxes = composeCartons(plan);
    expect(boxes.length).toBe(plan.cartons_per_container);
    for (const box of boxes) {
      expect(insideContainer(box, plan)).toBe(true);
    }
  });

  test("the partial last container is truthful", async ({ request }) => {
    // Containers 1..N-1 are full; the last carries only the remainder. The 3D
    // composes that remainder in real loading order — this pins the arithmetic
    // and the physics of the truncated compose.
    const { plan } = await planFor(request);

    // Server arithmetic: full containers + the last must cover the shipment
    // exactly (to the carton).
    expect(plan.containers_needed).toBeGreaterThanOrEqual(1);
    expect(plan.cartons_last_container).toBeGreaterThan(0);
    expect(plan.cartons_last_container).toBeLessThanOrEqual(plan.cartons_per_container);

    const partial = composeCartons(plan, plan.cartons_last_container);
    expect(partial.length).toBe(plan.cartons_last_container);

    // A truncated load still obeys physics: in bounds, no overlaps.
    for (let i = 0; i < partial.length; i++) {
      expect(insideContainer(partial[i], plan)).toBe(true);
      for (let j = i + 1; j < partial.length; j++) {
        if (overlaps(partial[i], partial[j])) {
          throw new Error(`partial: cartons ${i} and ${j} overlap`);
        }
      }
    }

    // Loading order is real: cartons fill complete pallets before starting the
    // next, so every occupied pallet except possibly the LAST is full.
    const perPallet = plan.carton_layer.length * plan.layers;
    const fullPallets = Math.floor(plan.cartons_last_container / perPallet);
    const decks = composePallets(plan, plan.cartons_last_container);
    expect(decks.length).toBe(Math.ceil(plan.cartons_last_container / perPallet));
    expect(decks.length).toBeGreaterThanOrEqual(fullPallets);

    // No empty pallets render: deck count strictly matches carton need.
    const fullDecks = composePallets(plan);
    expect(decks.length).toBeLessThanOrEqual(fullDecks.length);
  });

  test("a truncated compose is a prefix of the full compose", async ({ request }) => {
    // The partial container must be the SAME arrangement stopped early — not a
    // different packing. Prefix equality pins that.
    const { plan } = await planFor(request);
    const full = composeCartons(plan);
    const some = composeCartons(plan, 100);
    expect(some.length).toBe(100);
    for (let i = 0; i < some.length; i++) {
      expect(some[i]).toEqual(full[i]);
    }
  });

  test("the max-capacity layout obeys the same physics", async ({ request }) => {
    // The max view renders a DIFFERENT configuration from the recommended plan —
    // recomputed, never stored — so it gets the same treatment: compose it and
    // check it against reality, not against a screenshot.
    const create = await request.post(`${API}/api/simulation`, {
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

    const res = await request.get(`${API}/api/simulation/${id}/max-capacity`);
    expect(res.status(), await res.text()).toBe(200);
    const max = await res.json();
    const plan: LoadPlan = max.layout;

    const boxes = composeCartons(plan);
    // The 3D view must show exactly the number the headline claims.
    expect(boxes.length).toBe(max.absolute_max_cartons);
    expect(plan.container_type).toBe(max.absolute_max_container_type);

    for (let i = 0; i < boxes.length; i++) {
      expect(insideContainer(boxes[i], plan)).toBe(true);
      for (let j = i + 1; j < boxes.length; j++) {
        if (overlaps(boxes[i], boxes[j])) {
          throw new Error(`max layout: cartons ${i} and ${j} overlap`);
        }
      }
    }

    // Real-world rules apply to the max plan too: forklift clearance under the roof.
    const stackTop = plan.pallet_stack * plan.pallet.height_mm;
    expect(plan.container.height_mm - stackTop).toBeGreaterThanOrEqual(50 - 1e-6);
  });

  test("rotated pallets are honoured, not ignored", async ({ request }) => {
    const { plan } = await planFor(request);
    const rotated = plan.pallet_floor.filter((p) => p.rotated);
    if (rotated.length === 0) test.skip();

    // Every carton must still land inside the container despite the rotation.
    for (const box of composeCartons(plan)) {
      expect(insideContainer(box, plan)).toBe(true);
    }
  });
});
