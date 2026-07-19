"use client";

/**
 * 3D container load plan.
 *
 * Renders the layout the optimiser actually computed. It does not invent a
 * plausible-looking arrangement: the server sends one pallet layer and one
 * container floor as real placements, and this component composes the full load
 * by pure translation. It never decides where anything goes, because it can't —
 * for a `mixed` layer pattern, "12 cartons per layer" does not say where the
 * twelfth one sits.
 *
 * Loaded via next/dynamic from the results page: three.js is ~600 KB and must not
 * land on every page view.
 *
 * Coordinates
 * -----------
 * The API works in millimetres, origin at the lower-left of each area. Three.js
 * works in metres with Y up, so everything scales by 1/1000 and the API's (x, y)
 * footprint becomes the scene's (x, z).
 */

import { useMemo, useRef, useLayoutEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Edges, Bounds } from "@react-three/drei";
// `Edges` is still used on the container shell, just not on the (instanced) cartons.
import * as THREE from "three";
import type { LoadPlan } from "@/lib/api";
import { composeCartons, composePallets, MM, type Box } from "@/lib/load-plan";

// A hair of air between cartons so the block reads as individual boxes rather
// than one solid slab. Applied at render time only — the geometry the
// correctness tests check stays exact.
const CARTON_GAP_M = 0.012;

/** Every carton in one draw call — 1,440 individual meshes would not be viable. */
function Cartons({ boxes, cartonH }: { boxes: Box[]; cartonH: number }) {
  const ref = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    const shrink = (size: number) => Math.max(size - CARTON_GAP_M, size * 0.5);
    boxes.forEach((b, i) => {
      dummy.position.set(b.x, b.y, b.z);
      // Instances share one unit cube, so per-carton size is a scale.
      dummy.scale.set(shrink(b.l), shrink(cartonH), shrink(b.w));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.count = boxes.length;
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [boxes, cartonH]);

  // No <Edges> here: drei's Edges helper does not understand instancing, so it
  // draws the base cube's outline ONCE at the local origin instead of on each
  // carton — a stray 1 m wireframe box floating at the container corner. The gap
  // between cartons does the job of making individual boxes legible.
  return (
    <instancedMesh
      ref={ref}
      args={[undefined, undefined, Math.max(boxes.length, 1)]}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial
        color="#caa26c"
        roughness={0.8}
        metalness={0.02}
        flatShading
      />
    </instancedMesh>
  );
}

/** Pallet decks, so the double-stacking reads clearly. Only decks that carry
    at least one carton render — a part-full container has no empty pallets. */
function Pallets({ plan, cartonLimit }: { plan: LoadPlan; cartonLimit?: number }) {
  const decks = useMemo(() => composePallets(plan, cartonLimit), [plan, cartonLimit]);

  return (
    <>
      {decks.map((d, i) => (
        <mesh key={i} position={[d.x, d.y, d.z]} receiveShadow>
          <boxGeometry args={[d.l, d.h, d.w]} />
          <meshStandardMaterial color="#7d5f42" roughness={0.95} />
        </mesh>
      ))}
    </>
  );
}


/** The container shell — near-transparent so the load stays visible. */
function ContainerShell({ plan }: { plan: LoadPlan }) {
  const l = plan.container.length_mm * MM;
  const w = plan.container.width_mm * MM;
  const h = plan.container.height_mm * MM;

  return (
    <mesh position={[l / 2, h / 2, w / 2]}>
      <boxGeometry args={[l, h, w]} />
      <meshBasicMaterial
        transparent
        opacity={0.05}
        color="#3b82f6"
        depthWrite={false}
      />
      <Edges color="#3b82f6" />
    </mesh>
  );
}

function Scene({ plan, cartonLimit }: { plan: LoadPlan; cartonLimit?: number }) {
  const boxes = useMemo(() => composeCartons(plan, cartonLimit), [plan, cartonLimit]);
  const cartonH = plan.carton.height_mm * MM;
  const l = plan.container.length_mm * MM;
  const w = plan.container.width_mm * MM;
  const h = plan.container.height_mm * MM;

  return (
    <>
      {/* A 20GP is 6m and a 40HC is 12m, so no single camera distance frames both.
          Bounds fits the camera to whatever is actually there. */}
      <Bounds fit clip observe margin={1.15}>
        {/* Recentre so OrbitControls turns around the container, not the origin. */}
        <group position={[-l / 2, -h / 2, -w / 2]}>
          <ContainerShell plan={plan} />
          <Pallets plan={plan} cartonLimit={cartonLimit} />
          <Cartons boxes={boxes} cartonH={cartonH} />
        </group>
      </Bounds>

      {/* Plain lights only. drei's <Environment> fetches an HDR from a CDN, which
          fails offline and behind a strict CSP. */}
      <ambientLight intensity={0.75} />
      <hemisphereLight args={["#ffffff", "#64748b", 0.5]} />
      <directionalLight position={[8, 14, 6]} intensity={1.2} />
      <directionalLight position={[-8, 5, -6]} intensity={0.4} />

      <OrbitControls makeDefault enablePan minDistance={1} maxDistance={60} />
    </>
  );
}

export default function ContainerScene({
  plan,
  cartonLimit,
  label,
}: {
  plan: LoadPlan;
  /** Cartons actually aboard THIS container — the last one is usually short. */
  cartonLimit?: number;
  /** e.g. "Container 2 of 2 — partial load" */
  label?: string;
}) {
  const fullCount =
    plan.carton_layer.length *
    plan.layers *
    plan.pallet_floor.length *
    plan.pallet_stack;
  const cartonCount = Math.min(cartonLimit ?? fullCount, fullCount);
  const perPallet = plan.carton_layer.length * plan.layers;
  const palletCount =
    perPallet > 0
      ? Math.ceil(cartonCount / perPallet)
      : plan.pallet_floor.length * plan.pallet_stack;

  return (
    <div
      className="relative h-[28rem] rounded-md border bg-gradient-to-b from-slate-50 to-slate-200 dark:from-slate-900 dark:to-slate-950"
      data-testid="container-3d"
    >
      <Canvas
        dpr={[1, 2]}
        // Bounds overrides the distance; this only sets the viewing angle.
        camera={{ position: [1, 0.75, 1], fov: 45 }}
        // Without WebGL the canvas simply renders nothing; the caption below
        // still states the numbers, so the panel is never blank-and-silent.
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            3D view needs WebGL, which this browser does not provide.
          </div>
        }
      >
        <Scene plan={plan} cartonLimit={cartonLimit} />
      </Canvas>

      <div className="pointer-events-none absolute left-3 top-3 rounded bg-background/85 px-2.5 py-1.5 text-[11px] leading-relaxed shadow-sm backdrop-blur">
        <div className="font-medium">
          {plan.container_type}
          {label ? <span className="ml-1.5 font-normal text-muted-foreground">{label}</span> : null}
        </div>
        <div className="text-muted-foreground">
          {cartonCount.toLocaleString()} cartons ·{" "}
          {palletCount.toLocaleString()} pallets
        </div>
        <div className="text-muted-foreground">
          {/* Scaled to the cartons actually aboard — quoting the full-container
              density on a part-full load would overstate it. */}
          {((plan.capacity_utilization_pct * cartonCount) / fullCount).toFixed(1)}%
          packed · {plan.layer_pattern}
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-3 right-3 rounded bg-background/85 px-2 py-1 text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        drag to orbit · scroll to zoom
      </div>
    </div>
  );
}
