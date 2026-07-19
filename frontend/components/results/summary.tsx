"use client";

/**
 * Answer-first summary for the results page.
 *
 * The page used to open with three equal-weight package cards, and the number
 * everyone actually came for — "what do I save, what do I ship?" — lived in a
 * cost card below the fold. These two strips fix the hierarchy:
 *
 *   KpiStrip     — the four figures that answer the question in three seconds.
 *                  Savings is the hero (one hero per view); the rest are tiles.
 *   PipelineFlow — the product's story, pouch → carton → pallet → container,
 *                  with the key figure at each stage. The optimisation is a
 *                  chain of decisions; the UI should look like one.
 *
 * Styling notes (from the dataviz stat-tile spec): labels in sentence case with
 * muted ink, values semibold in text tokens (never a data color), proportional
 * figures for display numbers — tabular-nums is for aligned columns only.
 */

import type { SimulationDetail } from "@/lib/api";
import { Package, Box, Layers, Container, ChevronRight, TrendingDown } from "lucide-react";

function inr(val: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(val);
}

export function KpiStrip({ data }: { data: SimulationDetail }) {
  const cmp = data.comparison;
  const bc = data.best_container;
  if (!cmp || !bc) return null;

  const savingPct =
    cmp.total_cost_current > 0
      ? (cmp.total_savings / cmp.total_cost_current) * 100
      : 0;
  const saved = cmp.total_savings >= 0;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {/* Hero: the outcome */}
      <div className="col-span-2 rounded-lg border bg-card p-4 lg:col-span-1">
        <p className="text-sm text-muted-foreground">
          {saved ? "Saving vs current practice" : "Extra cost vs current practice"}
        </p>
        <p
          className={`mt-1 text-3xl font-semibold leading-none ${
            saved ? "text-success" : "text-destructive"
          }`}
        >
          {inr(Math.abs(cmp.total_savings))}
        </p>
        <p
          className={`mt-1.5 inline-flex items-center gap-1 text-xs font-medium ${
            saved ? "text-success" : "text-destructive"
          }`}
        >
          <TrendingDown className="h-3.5 w-3.5" aria-hidden />
          {saved ? "−" : "+"}
          {Math.abs(savingPct).toFixed(1)}% total cost
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm text-muted-foreground">Total cost</p>
        <p className="mt-1 text-2xl font-semibold leading-none">
          {inr(cmp.total_cost_ai)}
        </p>
        <p className="mt-1.5 text-xs text-muted-foreground">
          was {inr(cmp.total_cost_current)}
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm text-muted-foreground">Containers</p>
        <p className="mt-1 text-2xl font-semibold leading-none">
          {bc.containers_needed}
          <span className="ml-1.5 text-base font-medium text-muted-foreground">
            × {bc.container_type}
          </span>
        </p>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {bc.pallet_stack != null && bc.pallet_stack > 1
            ? `pallets stacked ${bc.pallet_stack}-high`
            : "floor-loaded pallets"}
        </p>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm text-muted-foreground">Container packed</p>
        <p className="mt-1 text-2xl font-semibold leading-none">
          {bc.capacity_utilization_pct ?? bc.utilization_pct}%
        </p>
        <p className="mt-1.5 text-xs text-muted-foreground">of a full container&apos;s volume</p>
      </div>
    </div>
  );
}

const STEP_ICONS = [Package, Box, Layers, Container] as const;

export function PipelineFlow({ data }: { data: SimulationDetail }) {
  const p = data.best_package;
  const c = data.carton;
  const pl = data.pallet;
  const bc = data.best_container;
  if (!p || !c || !pl || !bc) return null;

  const steps = [
    {
      name: "Pouch",
      figure: `${p.length_mm} × ${p.width_mm} × ${p.height_mm} mm`,
      detail: `${(p.fill_ratio * 100).toFixed(0)}% filled`,
    },
    {
      name: "Carton",
      figure: `${c.units_per_carton} pouches`,
      detail: `${c.carton_weight_kg} kg · ${c.board_grade}`,
    },
    {
      name: "Pallet",
      figure: `${pl.cartons_per_pallet} cartons`,
      detail: `${pl.cartons_per_layer}/layer × ${pl.layers}`,
    },
    {
      name: "Container",
      figure: `${bc.containers_needed} × ${bc.container_type}`,
      detail: `${bc.cartons_per_container.toLocaleString()} cartons each`,
    },
  ];

  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <ol className="grid grid-cols-2 gap-y-3 lg:flex lg:items-center lg:justify-between lg:gap-2">
        {steps.map((step, i) => {
          const Icon = STEP_ICONS[i];
          return (
            <li key={step.name} className="flex min-w-0 items-center gap-2">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary"
                aria-hidden
              >
                <Icon className="h-4.5 w-4.5" />
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] uppercase tracking-wide text-muted-foreground">
                  {step.name}
                </span>
                <span className="block truncate text-sm font-semibold">{step.figure}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {step.detail}
                </span>
              </span>
              {i < steps.length - 1 && (
                <ChevronRight
                  className="ml-2 hidden h-4 w-4 shrink-0 text-muted-foreground/50 lg:block"
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
