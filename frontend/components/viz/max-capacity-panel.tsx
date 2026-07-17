"use client";

/**
 * "How much fits in one container?" — the capacity ceiling for these inputs.
 *
 * A different question from the rest of the page. The results above answer "what
 * is the cheapest way to ship N pouches"; this answers "what is the most I could
 * ever get into one box", which is what someone quoting a container-load needs.
 *
 * Two honesty rules are baked into the presentation:
 *
 *  1. Max units compares fairly only WITHIN a container type. A 40HC holds more
 *     than a 20GP because it is a bigger box, not because it packs better, so
 *     the table shows "packed %" alongside — that is the cross-type measure — and
 *     says so in plain words.
 *  2. The verdict states whether the recommendation is already maximal. It
 *     usually is: filling a container fuller means fewer containers and less
 *     freight, so the cheapest plan and the fullest plan tend to coincide. If we
 *     showed a "max" without that context, a reader would assume the optimiser
 *     had missed something.
 *
 * Loaded on click — the endpoint re-runs the search (~1s), so nobody pays for a
 * question they didn't ask.
 */

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Gauge, Info, CheckCircle2 } from "lucide-react";
import { getMaxCapacity, type MaxCapacity, type MaxCapacityOption } from "@/lib/api";

function tonnes(kg: number) {
  return `${(kg / 1000).toFixed(1)} t`;
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

/** The pouch → carton → pallet that achieves the headline number. */
function AchievingConfig({ option }: { option: MaxCapacityOption }) {
  const { package: pkg, carton, pallet } = option;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <div className="space-y-2 rounded-md border p-3 text-sm">
        <p className="font-semibold">Pouch</p>
        <Detail
          label="Dimensions"
          value={`${pkg.length_mm} × ${pkg.width_mm} × ${pkg.height_mm} mm`}
        />
        <Detail label="Product Volume" value={`${pkg.product_volume_cm3} cm³`} />
        <Detail label="Pouch Volume" value={`${pkg.volume_cm3} cm³`} />
        <Detail label="Fill Ratio" value={`${(pkg.fill_ratio * 100).toFixed(1)}%`} />
        <Detail label="Cost" value={`₹${pkg.cost_estimate.toFixed(3)} / unit`} />
      </div>

      <div className="space-y-2 rounded-md border p-3 text-sm">
        <p className="font-semibold">Carton</p>
        <Detail
          label="Outer Dimensions"
          value={`${carton.outer_length_mm} × ${carton.outer_width_mm} × ${carton.outer_height_mm} mm`}
        />
        <Detail
          label="Units Per Carton"
          value={`${carton.units_per_carton} (${carton.arrangement})`}
        />
        <Detail label="Carton Weight" value={`${carton.carton_weight_kg} kg`} />
        <Detail label="Board Grade" value={carton.board_grade} />
      </div>

      <div className="space-y-2 rounded-md border p-3 text-sm">
        <p className="font-semibold">Pallet</p>
        <Detail label="Cartons Per Layer" value={pallet.cartons_per_layer} />
        <Detail label="Layers" value={pallet.layers} />
        <Detail label="Cartons Per Pallet" value={pallet.cartons_per_pallet} />
        <Detail label="Pallet Height" value={`${pallet.pallet_height_m} m`} />
        <Detail label="Footprint Used" value={`${pallet.footprint_utilization_pct}%`} />
      </div>
    </div>
  );
}

export function MaxCapacityPanel({ simulationId }: { simulationId: string }) {
  const [data, setData] = useState<MaxCapacity | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getMaxCapacity(simulationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not work out the capacity");
    } finally {
      setLoading(false);
    }
  }

  const headline = data?.options.find(
    (o) => o.container_type === data.absolute_max_container_type
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Gauge className="h-5 w-5 text-primary" /> Maximum Capacity
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!data && !loading && (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-10">
            <p className="max-w-lg text-center text-sm text-muted-foreground">
              The results above show the cheapest way to ship your order. This
              answers a different question: with these same tea and pouch settings,
              what is the <strong>most</strong> you could fit into one container?
            </p>
            <Button variant="outline" size="sm" onClick={load}>
              <Gauge className="mr-1 h-4 w-4" /> Optimize for maximum
            </Button>
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center gap-2 rounded-md border py-10 text-sm text-muted-foreground">
            <Spinner size="sm" /> Searching every configuration…
          </div>
        )}

        {data && headline && (
          <div className="space-y-4">
            {/* Headline */}
            <div className="rounded-md border bg-primary/5 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Most that fits in one container
              </p>
              <p className="mt-1 text-2xl font-bold">
                {data.absolute_max_units.toLocaleString()} pouches
                <span className="ml-2 text-base font-normal text-muted-foreground">
                  in one {data.absolute_max_container_type}
                </span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                = {data.absolute_max_cartons.toLocaleString()} cartons ·{" "}
                {tonnes(data.absolute_max_tea_weight_kg)} of tea
              </p>
            </div>

            {/* The honest reading of the numbers */}
            <div
              className={`flex gap-2 rounded-md border p-3 text-sm ${
                data.already_maximal
                  ? "border-success/40 bg-success/5"
                  : "border-warning/40 bg-warning/5"
              }`}
            >
              {data.already_maximal ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-success mt-0.5" aria-hidden />
              ) : (
                <Info className="h-4 w-4 shrink-0 text-warning mt-0.5" aria-hidden />
              )}
              <p className="leading-relaxed">{data.verdict}</p>
            </div>

            {/* Per container type */}
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Container</TableHead>
                    <TableHead className="text-right">Max Cartons</TableHead>
                    <TableHead className="text-right">Max Quantity</TableHead>
                    <TableHead className="text-right">Tea Weight</TableHead>
                    <TableHead
                      className="text-right"
                      title="Share of the container's volume filled — the fair way to compare types"
                    >
                      Packed
                    </TableHead>
                    <TableHead className="text-right">Limited By</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.options.map((o) => (
                    <TableRow
                      key={o.container_type}
                      className={
                        o.container_type === data.absolute_max_container_type
                          ? "bg-primary/5"
                          : ""
                      }
                    >
                      <TableCell className="font-medium">
                        {o.container_type}
                        {o.is_recommended_type && (
                          <Badge variant="secondary" className="ml-2 text-[10px]">
                            recommended
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {o.max_cartons_per_container.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {o.max_units_per_container.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        {tonnes(o.max_tea_weight_kg)}
                      </TableCell>
                      <TableCell className="text-right">
                        {o.capacity_utilization_pct}%
                      </TableCell>
                      <TableCell className="text-right capitalize text-muted-foreground">
                        {o.limited_by}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* The caveat that stops a bigger box reading as better packing */}
            <p className="text-xs text-muted-foreground leading-relaxed">
              A {data.absolute_max_container_type} holds the most simply because it
              is the largest box — not because it packs better.{" "}
              <strong>Packed</strong> is the fair comparison: it is how much of each
              container actually holds tea.{" "}
              {headline.limited_by === "volume" &&
                "All three run out of space long before they run out of weight allowance — tea is light, so these loads are volume-limited."}
            </p>

            {/* Same detail level as the recommendation above */}
            <div>
              <p className="mb-2 text-sm font-semibold">
                The packing that achieves it ({data.absolute_max_container_type})
              </p>
              <AchievingConfig option={headline} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
