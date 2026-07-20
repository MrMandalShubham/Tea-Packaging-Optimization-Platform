"use client";

/**
 * Container Loading — one panel, two questions, a single switch between them.
 *
 * The page answers two container questions that people kept confusing:
 *
 *   "For your order"        — how the shipment you entered actually ships
 *                             (N pouches → this many containers, this full).
 *   "Maximum per container" — the ceiling: the most that fits in ONE container
 *                             of each type, ignoring your order size.
 *
 * They used to live in three separate places (a comparison table, a max-capacity
 * card, and a 3D panel), so a reader had to assemble the story themselves. Here
 * both modes render the *same* ordered layout — headline → stacking chain → fill
 * → per-container table → 3D — so the two answers are directly comparable and the
 * multiplication that produces each number is visible, not asserted.
 *
 * The max mode is fetched on first switch (~1s search); nobody pays for a
 * question they didn't ask.
 */

import { useState } from "react";
import dynamic from "next/dynamic";
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
import { Boxes, CheckCircle2, Info, Layers as LayersIcon } from "lucide-react";
import {
  getLoadPlan,
  getMaxCapacity,
  type SimulationDetail,
  type LoadPlan,
  type MaxCapacity,
} from "@/lib/api";

// Same lazy three.js scene both the order and max views draw with — one chunk.
const ContainerScene = dynamic(() => import("../viz/container-scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[28rem] items-center justify-center rounded-md border">
      <Spinner size="lg" />
    </div>
  ),
});

function inr(v: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(v);
}
function num(v: number) {
  return v.toLocaleString("en-IN");
}
function tonnes(kg: number) {
  return `${(kg / 1000).toFixed(1)} t`;
}

// ── The shared, self-explanatory pieces ───────────────────────────────────────

/**
 * The whole capacity story is one multiplication:
 *   units/carton × cartons/pallet × pallets/container = units/container.
 * Showing it as a chain means the final number is never a figure to trust — it
 * is a figure to check. Identical in both modes.
 */
interface Chain {
  unitsPerCarton: number;
  arrangement?: string;
  cartonsPerLayer: number;
  layers: number;
  cartonsPerPallet: number;
  palletsPerContainer: number | null;
  palletStack: number | null;
  cartonsPerContainer: number;
  unitsPerContainer: number;
}

function ChainTile({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`min-w-[7.5rem] flex-1 rounded-md border p-3 text-center ${
        highlight ? "border-primary/50 bg-primary/5" : "bg-card"
      }`}
    >
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function Op({ children }: { children: string }) {
  return (
    <div className="flex items-center justify-center px-0.5 text-lg font-medium text-muted-foreground/70">
      {children}
    </div>
  );
}

function StackingChain({ chain }: { chain: Chain }) {
  const floorPallets =
    chain.palletsPerContainer != null && chain.palletStack
      ? chain.palletsPerContainer / chain.palletStack
      : null;
  return (
    <div className="flex flex-wrap items-stretch gap-1">
      <ChainTile
        label="Units / carton"
        value={num(chain.unitsPerCarton)}
        sub={chain.arrangement}
      />
      <Op>×</Op>
      <ChainTile
        label="Cartons / pallet"
        value={num(chain.cartonsPerPallet)}
        sub={`${chain.cartonsPerLayer}/layer × ${chain.layers} layers`}
      />
      <Op>×</Op>
      <ChainTile
        label="Pallets / container"
        value={chain.palletsPerContainer != null ? num(chain.palletsPerContainer) : "—"}
        sub={
          floorPallets && chain.palletStack && chain.palletStack > 1
            ? `${floorPallets} floor × ${chain.palletStack} high`
            : "floor-loaded"
        }
      />
      <Op>=</Op>
      <ChainTile
        label="Units / container"
        value={num(chain.unitsPerContainer)}
        sub={`${num(chain.cartonsPerContainer)} cartons`}
        highlight
      />
    </div>
  );
}

/** Packed vs empty, drawn to scale so "68% full" looks like 68% full. */
function FillBar({ packed, note }: { packed: number; note?: React.ReactNode }) {
  const empty = Math.max(0, 100 - packed);
  return (
    <div className="space-y-1.5">
      <div className="flex h-3 overflow-hidden rounded-full border">
        <div className="bg-primary" style={{ width: `${packed}%` }} aria-hidden />
        <div className="bg-muted" style={{ width: `${empty}%` }} aria-hidden />
      </div>
      <div className="flex flex-wrap justify-between gap-x-4 text-xs text-muted-foreground">
        <span>
          <span className="font-semibold text-foreground">{packed.toFixed(1)}%</span> packed
          with cartons
        </span>
        <span>
          <span className="font-semibold text-foreground">{empty.toFixed(1)}%</span> empty
          {note ? <> · {note}</> : null}
        </span>
      </div>
    </div>
  );
}

// ── 3D, shared, with the recommended-plan container selector ──────────────────

function LoadScene({
  plan,
  order,
}: {
  plan: LoadPlan;
  order: boolean;
}) {
  // Only the order view books more than one container; max is always one.
  const [selected, setSelected] = useState(1);
  const n = order ? plan.containers_needed : 1;
  const isLast = selected === n;
  const cartonLimit = order
    ? isLast
      ? plan.cartons_last_container
      : plan.cartons_per_container
    : undefined;
  const isPartial =
    cartonLimit != null && cartonLimit < plan.cartons_per_container;

  return (
    <div data-testid={order ? "order-3d" : "max-3d"}>
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
            This container carries {cartonLimit!.toLocaleString()} of a possible{" "}
            {plan.cartons_per_container.toLocaleString()} cartons — the shipment&apos;s
            remainder, loaded in real order: full pallets first, complete layers before
            the last. The empty space is real; you pay freight on it.
          </>
        ) : (
          <>
            Rendered from the computed load plan — {plan.carton_layer.length} cartons/layer
            × {plan.layers} layers × {plan.pallet_floor.length} pallets ×{" "}
            {plan.pallet_stack} high. Cartons use outer dimensions, so the board you see is
            real.
          </>
        )}
      </p>
    </div>
  );
}

function ThreeDToggle({
  order,
  load,
  plan,
  loading,
}: {
  order: boolean;
  load: () => void;
  plan: LoadPlan | null;
  loading: boolean;
}) {
  if (plan) return <LoadScene plan={plan} order={order} />;
  if (loading)
    return (
      <div className="flex h-[28rem] items-center justify-center rounded-md border">
        <Spinner size="lg" />
      </div>
    );
  return (
    <div className="flex justify-center">
      <Button variant="outline" size="sm" onClick={load}>
        <Boxes className="mr-1 h-4 w-4" /> View this load in 3D
      </Button>
    </div>
  );
}

// ── The panel ─────────────────────────────────────────────────────────────────

export function ContainerLoadingPanel({
  data,
  simulationId,
}: {
  data: SimulationDetail;
  simulationId: string;
}) {
  const [mode, setMode] = useState<"order" | "max">("order");

  // Max capacity — lazy on first switch.
  const [max, setMax] = useState<MaxCapacity | null>(null);
  const [maxLoading, setMaxLoading] = useState(false);
  const [maxError, setMaxError] = useState<string | null>(null);

  // 3D plans — lazy per mode.
  const [orderPlan, setOrderPlan] = useState<LoadPlan | null>(null);
  const [orderPlanLoading, setOrderPlanLoading] = useState(false);
  const [max3dLoading] = useState(false);
  const [maxPlanShown, setMaxPlanShown] = useState(false);

  const bc = data.best_container;
  const carton = data.carton;
  const pallet = data.pallet;
  const pkg = data.best_package;
  const allContainers = bc ? [bc, ...data.container_alternatives] : [];

  async function switchTo(next: "order" | "max") {
    setMode(next);
    if (next === "max" && !max && !maxLoading) {
      setMaxLoading(true);
      setMaxError(null);
      try {
        setMax(await getMaxCapacity(simulationId));
      } catch (e) {
        setMaxError(e instanceof Error ? e.message : "Could not work out the capacity");
      } finally {
        setMaxLoading(false);
      }
    }
  }

  async function loadOrderPlan() {
    setOrderPlanLoading(true);
    try {
      setOrderPlan(await getLoadPlan(simulationId));
    } catch {
      /* the empty-state button stays; a retry is one more click */
    } finally {
      setOrderPlanLoading(false);
    }
  }

  if (!bc || !carton || !pallet || !pkg) return null;

  const qty = data.inputs?.shipment_quantity ?? bc.total_units_shipped;

  return (
    <Card className="no-print">
      <CardHeader className="gap-3">
        <CardTitle className="text-base flex items-center gap-2">
          <LayersIcon className="h-5 w-5 text-primary" /> Container Loading
        </CardTitle>
        {/* The switch. Two questions, one place. */}
        <div className="inline-flex w-fit rounded-lg border bg-muted/40 p-0.5 text-sm">
          <button
            onClick={() => switchTo("order")}
            className={`rounded-md px-3 py-1.5 font-medium transition ${
              mode === "order"
                ? "bg-background shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            For your order
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
              {num(qty)} pouches
            </span>
          </button>
          <button
            onClick={() => switchTo("max")}
            className={`rounded-md px-3 py-1.5 font-medium transition ${
              mode === "max"
                ? "bg-background shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Maximum per container
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
              most in one
            </span>
          </button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {/* ══ ORDER MODE ══ */}
        {mode === "order" && (
          <>
            {/* 1. Headline */}
            <div className="rounded-md border bg-primary/5 p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Your order ships as
              </p>
              <p className="mt-1 text-2xl font-bold">
                {bc.containers_needed} × {bc.container_type}
                <span className="ml-2 text-base font-normal text-muted-foreground">
                  for {num(qty)} pouches
                </span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {num(bc.cartons_per_container)} cartons per full container ·{" "}
                {bc.capacity_utilization_pct}% packed
              </p>
            </div>

            {/* 2. Stacking chain */}
            <div className="space-y-1.5">
              <p className="text-sm font-semibold">How one container is built</p>
              <StackingChain
                chain={{
                  unitsPerCarton: carton.units_per_carton,
                  arrangement: carton.arrangement ?? undefined,
                  cartonsPerLayer: pallet.cartons_per_layer,
                  layers: pallet.layers,
                  cartonsPerPallet: pallet.cartons_per_pallet,
                  palletsPerContainer: bc.pallets_per_container,
                  palletStack: bc.pallet_stack,
                  cartonsPerContainer: bc.cartons_per_container,
                  unitsPerContainer: bc.units_per_container,
                }}
              />
            </div>

            {/* 3. Fill */}
            <FillBar
              packed={bc.capacity_utilization_pct}
              note="pallet decks + floor gaps + roof clearance"
            />

            {/* 4. Per-container table (both views: full container + this order) */}
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead rowSpan={2} className="align-bottom">Container</TableHead>
                    <TableHead colSpan={3} className="border-l text-center text-xs">
                      One full container
                    </TableHead>
                    <TableHead colSpan={3} className="border-l text-center text-xs">
                      This order
                    </TableHead>
                    <TableHead rowSpan={2} className="align-bottom border-l">Best</TableHead>
                  </TableRow>
                  <TableRow>
                    <TableHead className="border-l text-right">Cartons</TableHead>
                    <TableHead className="text-right">Units</TableHead>
                    <TableHead className="text-right">Packed</TableHead>
                    <TableHead className="border-l text-right">Needed</TableHead>
                    <TableHead className="text-right">Used</TableHead>
                    <TableHead className="text-right">Freight</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allContainers.map((c) => (
                    <TableRow key={c.container_type} className={c.is_best ? "bg-primary/5" : ""}>
                      <TableCell className="font-medium">
                        {c.container_type}
                        {c.pallet_stack != null && c.pallet_stack > 1 && (
                          <span className="block text-[10px] text-muted-foreground">
                            pallets {c.pallet_stack}-high
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="border-l text-right">{num(c.cartons_per_container)}</TableCell>
                      <TableCell className="text-right">{num(c.units_per_container)}</TableCell>
                      <TableCell className="text-right">{c.capacity_utilization_pct}%</TableCell>
                      <TableCell className="border-l text-right font-medium">{c.containers_needed}</TableCell>
                      <TableCell className="text-right">{c.utilization_pct}%</TableCell>
                      <TableCell className="text-right">{inr(c.freight_cost)}</TableCell>
                      <TableCell className="border-l">
                        {c.is_best && <Badge variant="success">Best</Badge>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* 5. 3D */}
            <ThreeDToggle
              order
              load={loadOrderPlan}
              plan={orderPlan}
              loading={orderPlanLoading}
            />
          </>
        )}

        {/* ══ MAX MODE ══ */}
        {mode === "max" && (
          <>
            {maxLoading && (
              <div className="flex items-center justify-center gap-2 rounded-md border py-10 text-sm text-muted-foreground">
                <Spinner size="sm" /> Searching every configuration…
              </div>
            )}
            {maxError && (
              <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                {maxError}
              </p>
            )}
            {max &&
              (() => {
                const head = max.options.find(
                  (o) => o.container_type === max.absolute_max_container_type
                );
                if (!head) return null;
                return (
                  <>
                    {/* 1. Headline */}
                    <div className="rounded-md border bg-primary/5 p-4">
                      <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Most that fits in one container
                      </p>
                      <p className="mt-1 text-2xl font-bold">
                        {num(max.absolute_max_units)} pouches
                        <span className="ml-2 text-base font-normal text-muted-foreground">
                          in one {max.absolute_max_container_type}
                        </span>
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        = {num(max.absolute_max_cartons)} cartons ·{" "}
                        {tonnes(max.absolute_max_tea_weight_kg)} of tea
                      </p>
                    </div>

                    {/* Honest reading */}
                    <div
                      className={`flex gap-2 rounded-md border p-3 text-sm ${
                        max.already_maximal
                          ? "border-success/40 bg-success/5"
                          : "border-warning/40 bg-warning/5"
                      }`}
                    >
                      {max.already_maximal ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
                      ) : (
                        <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
                      )}
                      <p className="leading-relaxed">{max.verdict}</p>
                    </div>

                    {/* 2. Stacking chain */}
                    <div className="space-y-1.5">
                      <p className="text-sm font-semibold">
                        How the fullest {max.absolute_max_container_type} is built
                      </p>
                      <StackingChain
                        chain={{
                          unitsPerCarton: head.carton.units_per_carton,
                          arrangement: head.carton.arrangement,
                          cartonsPerLayer: head.pallet.cartons_per_layer,
                          layers: head.pallet.layers,
                          cartonsPerPallet: head.pallet.cartons_per_pallet,
                          palletsPerContainer: head.pallets_per_container,
                          palletStack: head.pallet_stack,
                          cartonsPerContainer: head.max_cartons_per_container,
                          unitsPerContainer: head.max_units_per_container,
                        }}
                      />
                    </div>

                    {/* 3. Fill */}
                    <FillBar
                      packed={head.capacity_utilization_pct}
                      note={`${head.limited_by}-limited`}
                    />

                    {/* 4. Per-container-type table */}
                    <div className="rounded-md border overflow-x-auto">
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
                          {max.options.map((o) => (
                            <TableRow
                              key={o.container_type}
                              className={
                                o.container_type === max.absolute_max_container_type
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
                                {num(o.max_cartons_per_container)}
                              </TableCell>
                              <TableCell className="text-right font-medium">
                                {num(o.max_units_per_container)}
                              </TableCell>
                              <TableCell className="text-right">{tonnes(o.max_tea_weight_kg)}</TableCell>
                              <TableCell className="text-right">{o.capacity_utilization_pct}%</TableCell>
                              <TableCell className="text-right capitalize text-muted-foreground">
                                {o.limited_by}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>

                    <p className="text-xs leading-relaxed text-muted-foreground">
                      A {max.absolute_max_container_type} holds the most simply because it is
                      the largest box — not because it packs better. <strong>Packed</strong> is
                      the fair comparison across types.
                    </p>

                    {/* 5. 3D */}
                    {maxPlanShown ? (
                      <LoadScene plan={max.layout} order={false} />
                    ) : (
                      <div className="flex justify-center">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setMaxPlanShown(true)}
                          disabled={max3dLoading}
                        >
                          <Boxes className="mr-1 h-4 w-4" /> View this load in 3D
                        </Button>
                      </div>
                    )}
                  </>
                );
              })()}
          </>
        )}
      </CardContent>
    </Card>
  );
}
