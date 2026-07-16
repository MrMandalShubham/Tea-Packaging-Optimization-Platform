/**
 * Load-plan geometry — pure maths, no three.js.
 *
 * Kept apart from the renderer for one reason: this is the part that can be
 * wrong. A 3D view that silently misplaces cartons looks exactly like one that
 * doesn't, so the composition has to be testable without a WebGL context.
 *
 * Nothing here decides where anything goes. The server sends the real placements
 * the optimiser computed; this only repeats them — across the layers of a pallet,
 * the pallets on a floor, and the tiers of a stack.
 */

import type { LoadPlan } from "@/lib/api";

export const MM = 0.001; // millimetres → metres

/** A carton's world centre and footprint, in metres. Y is up. */
export interface Box {
  x: number;
  y: number;
  z: number;
  l: number; // extent along world X
  w: number; // extent along world Z
  h: number; // extent along world Y
}

/**
 * Expand the recipe into every carton position.
 *
 *   pallets on floor × pallets stacked high × cartons per layer × layers
 *
 * A rotated pallet turns its whole load with it. Mapping pallet-local (lx, lz) to
 * world for a pallet turned 90°: the local length axis runs along world −Z, so
 * `world_x = px + lz` and `world_z = pz + PALLET_L − lx`, and the carton's own
 * footprint swaps with it.
 */
export function composeCartons(plan: LoadPlan): Box[] {
  const boxes: Box[] = [];
  const cartonH = plan.carton.height_mm * MM;
  const deck = plan.pallet_base_height_mm * MM;
  const palletH = plan.pallet.height_mm * MM;
  const palletL = plan.pallet.length_mm * MM;

  for (const pallet of plan.pallet_floor) {
    const px = pallet.x * MM;
    const pz = pallet.y * MM;

    for (let tier = 0; tier < plan.pallet_stack; tier++) {
      const base = tier * palletH + deck;

      for (const c of plan.carton_layer) {
        // Carton footprint in pallet-local space.
        const cl = (c.rotated ? plan.carton.width_mm : plan.carton.length_mm) * MM;
        const cw = (c.rotated ? plan.carton.length_mm : plan.carton.width_mm) * MM;
        const lx = c.x * MM;
        const lz = c.y * MM;

        let wx: number, wz: number, wl: number, ww: number;
        if (pallet.rotated) {
          wx = px + lz + cw / 2;
          wz = pz + palletL - lx - cl / 2;
          wl = cw;
          ww = cl;
        } else {
          wx = px + lx + cl / 2;
          wz = pz + lz + cw / 2;
          wl = cl;
          ww = cw;
        }

        for (let layer = 0; layer < plan.layers; layer++) {
          boxes.push({
            x: wx,
            y: base + layer * cartonH + cartonH / 2,
            z: wz,
            l: wl,
            w: ww,
            h: cartonH,
          });
        }
      }
    }
  }
  return boxes;
}

/** Pallet decks, in world space. */
export function composePallets(plan: LoadPlan): Box[] {
  const deck = plan.pallet_base_height_mm * MM;
  const palletH = plan.pallet.height_mm * MM;
  const out: Box[] = [];

  for (const p of plan.pallet_floor) {
    const l = (p.rotated ? plan.pallet.width_mm : plan.pallet.length_mm) * MM;
    const w = (p.rotated ? plan.pallet.length_mm : plan.pallet.width_mm) * MM;
    for (let tier = 0; tier < plan.pallet_stack; tier++) {
      out.push({
        x: p.x * MM + l / 2,
        y: tier * palletH + deck / 2,
        z: p.y * MM + w / 2,
        l,
        w,
        h: deck,
      });
    }
  }
  return out;
}

/** Do two boxes share volume? Touching faces are fine; overlap is not. */
export function overlaps(a: Box, b: Box, tol = 1e-6): boolean {
  return (
    Math.abs(a.x - b.x) < (a.l + b.l) / 2 - tol &&
    Math.abs(a.y - b.y) < (a.h + b.h) / 2 - tol &&
    Math.abs(a.z - b.z) < (a.w + b.w) / 2 - tol
  );
}

/** Is a box fully inside the container shell? */
export function insideContainer(box: Box, plan: LoadPlan, tol = 1e-6): boolean {
  const L = plan.container.length_mm * MM;
  const W = plan.container.width_mm * MM;
  const H = plan.container.height_mm * MM;
  return (
    box.x - box.l / 2 >= -tol &&
    box.x + box.l / 2 <= L + tol &&
    box.z - box.w / 2 >= -tol &&
    box.z + box.w / 2 <= W + tol &&
    box.y - box.h / 2 >= -tol &&
    box.y + box.h / 2 <= H + tol
  );
}
