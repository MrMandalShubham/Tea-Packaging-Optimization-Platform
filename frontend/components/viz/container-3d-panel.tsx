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

  async function open() {
    setLoading(true);
    setError(null);
    try {
      setPlan(await getLoadPlan(simulationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the load plan");
    } finally {
      setLoading(false);
    }
  }

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
            <ContainerScene plan={plan} />
            <p className="mt-2 text-xs text-muted-foreground">
              Rendered from the computed load plan — {plan.carton_layer.length}{" "}
              cartons per layer × {plan.layers} layers ×{" "}
              {plan.pallet_floor.length} pallets ×{" "}
              {plan.pallet_stack} high. Cartons use outer dimensions, so the board
              thickness you see is real.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
