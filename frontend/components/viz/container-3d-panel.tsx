"use client";

/**
 * Results-page panel wrapping the 3D load plan.
 *
 * Two things happen here, both deliberate:
 *
 *  1. The three.js scene is `next/dynamic` with `ssr: false`. It is ~600 KB and
 *     needs a real WebGL context, so it must not be in the server render or the
 *     initial bundle. It is fetched when the user opens the panel, in the same
 *     spirit as the lazy `xlsx` import in lib/export.ts.
 *  2. The load plan is fetched on open, not on page load. Nobody pays for a view
 *     they never look at.
 */

import { useState } from "react";
import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Boxes } from "lucide-react";
import { getLoadPlan, type LoadPlan } from "@/lib/api";

const ContainerScene = dynamic(() => import("./container-scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[28rem] items-center justify-center rounded-md border">
      <Spinner size="lg" />
    </div>
  ),
});

export function Container3DPanel({ simulationId }: { simulationId: string }) {
  const [plan, setPlan] = useState<LoadPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 1-based index of the container being viewed. Containers 1..N-1 are identical
  // full loads; the LAST carries only the shipment's remainder — and for a
  // sub-container order the only container IS the partial one.
  const [selected, setSelected] = useState(1);

  async function open() {
    setLoading(true);
    setError(null);
    try {
      const p = await getLoadPlan(simulationId);
      setPlan(p);
      setSelected(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the load plan");
    } finally {
      setLoading(false);
    }
  }

  const n = plan?.containers_needed ?? 1;
  const isLast = selected === n;
  // Full containers carry the full recipe; the last carries the remainder.
  const cartonLimit = plan
    ? isLast
      ? plan.cartons_last_container
      : plan.cartons_per_container
    : undefined;
  const isPartial =
    plan != null && cartonLimit != null && cartonLimit < plan.cartons_per_container;

  return (
    <Card className="no-print">
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Boxes className="h-5 w-5 text-primary" /> 3D Container Load
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!plan && !loading && (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-10">
            <p className="max-w-md text-center text-sm text-muted-foreground">
              See exactly how the recommended container is loaded — every carton
              placed where the optimiser put it.
            </p>
            <Button variant="outline" size="sm" onClick={open}>
              <Boxes className="mr-1 h-4 w-4" /> Load 3D view
            </Button>
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}

        {loading && (
          <div className="flex h-[28rem] items-center justify-center rounded-md border">
            <Spinner size="lg" />
          </div>
        )}

        {plan && (
          <>
            {/* Container selector — only when the shipment books more than one.
                Chips up to 6; a dropdown past that (a 20-chip row helps nobody). */}
            {n > 1 && (
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">Viewing:</span>
                {n <= 6 ? (
                  Array.from({ length: n }, (_, i) => i + 1).map((i) => (
                    <Button
                      key={i}
                      size="sm"
                      variant={selected === i ? "default" : "outline"}
                      className="h-7 px-2.5 text-xs"
                      onClick={() => setSelected(i)}
                    >
                      Container {i}
                      {i === n && plan.cartons_last_container < plan.cartons_per_container
                        ? " (partial)"
                        : ""}
                    </Button>
                  ))
                ) : (
                  <select
                    className="h-8 rounded-md border bg-background px-2 text-xs"
                    value={selected}
                    onChange={(e) => setSelected(Number(e.target.value))}
                    aria-label="Select container"
                  >
                    {Array.from({ length: n }, (_, i) => i + 1).map((i) => (
                      <option key={i} value={i}>
                        Container {i}
                        {i === n && plan.cartons_last_container < plan.cartons_per_container
                          ? " (partial)"
                          : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}

            <ContainerScene
              plan={plan}
              cartonLimit={cartonLimit}
              label={
                n > 1
                  ? `container ${selected} of ${n}${isPartial ? " — partial" : ""}`
                  : isPartial
                  ? "partial load"
                  : undefined
              }
            />
            <p className="mt-2 text-xs text-muted-foreground">
              {isPartial ? (
                <>
                  Container {selected} carries the shipment&apos;s remainder —{" "}
                  {cartonLimit!.toLocaleString()} of a possible{" "}
                  {plan.cartons_per_container.toLocaleString()} cartons, loaded in
                  real packing order: full pallets first, then a part-filled
                  pallet, complete layers before the last. The empty space you
                  see is real — it ships, and you pay freight on it.
                </>
              ) : (
                <>
                  Rendered from the computed load plan — {plan.carton_layer.length}{" "}
                  cartons per layer × {plan.layers} layers ×{" "}
                  {plan.pallet_floor.length} pallets × {plan.pallet_stack} high.
                  Cartons use outer dimensions, so the board thickness you see is
                  real.
                </>
              )}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
