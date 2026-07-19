"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getReferenceData, type ReferenceData } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { FlaskConical } from "lucide-react";

const SHIPMENT_TYPE_OPTIONS = [
  { value: "total_weight", label: "Total Order" },
  { value: "per_container", label: "Per Container" },
];

/**
 * Fallbacks used only if GET /api/reference is unreachable, so the form still
 * works against a cold backend. The database is the source of truth — these are
 * a liferaft, not a second copy of the catalogue.
 */
const FALLBACK_WEIGHTS = [
  { value: "100", label: "100 g" },
  { value: "250", label: "250 g" },
  { value: "500", label: "500 g" },
  { value: "1000", label: "1 kg" },
];
const FALLBACK_SHAPES = [
  { value: "square", label: "Square / Rectangular" },
  { value: "round", label: "Round / Cylindrical" },
];
const FALLBACK_MATERIALS = [
  { value: "paper", label: "Paper / Kraft" },
  { value: "plastic", label: "Plastic / LDPE" },
  { value: "metal", label: "Metal / Foil Laminate" },
];
const FALLBACK_PALLETS = [
  { value: "industrial", label: "Industrial 1200×1000" },
  { value: "eur1", label: "EUR / EPAL 1200×800" },
  { value: "gma", label: "US GMA 48×40 in (1219×1016)" },
];

export default function NewSimulationPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    tea_density: "0.35",
    package_weight: "250",
    shipment_quantity: "100000",
    shipment_type: "total_weight",
    package_shape: "square",
    packaging_material: "paper",
    target_market: "",
    pallet_type: "industrial",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ref, setRef] = useState<ReferenceData | null>(null);

  // Dropdown options and validation bounds come from the server, so the SKUs and
  // limits offered here are the same ones the API enforces.
  useEffect(() => {
    getReferenceData()
      .then((r) => {
        setRef(r);
        const preferred = r.package_weights.find((w) => w.is_default);
        if (preferred) {
          setForm((prev) => ({ ...prev, package_weight: String(preferred.grams) }));
        }
      })
      .catch(() => setRef(null)); // fall back to the static lists below
  }, []);

  const weightOptions =
    ref?.package_weights.map((w) => ({ value: String(w.grams), label: w.label })) ??
    FALLBACK_WEIGHTS;
  const shapeOptions =
    ref?.package_types.map((t) => ({ value: t.key, label: t.name })) ?? FALLBACK_SHAPES;
  const materialOptions =
    ref?.materials.map((m) => ({ value: m.key, label: m.name })) ?? FALLBACK_MATERIALS;
  const palletOptions =
    ref?.pallet_types?.map((p) => ({ value: p.key, label: p.name })) ?? FALLBACK_PALLETS;

  const minWeight = ref?.min_package_weight_g ?? 1;
  const maxWeight = ref?.max_package_weight_g ?? 5000;
  const minDensity = ref?.min_tea_density ?? 0.01;
  const maxDensity = ref?.max_tea_density ?? 5;

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const density = parseFloat(form.tea_density);
    const weight = parseFloat(form.package_weight);
    const qty = parseInt(form.shipment_quantity);

    if (!density || density < minDensity || density > maxDensity) {
      setError(`Tea density must be between ${minDensity}–${maxDensity} g/cm³`);
      return;
    }
    if (!weight || weight < minWeight || weight > maxWeight) {
      setError(`Package weight must be between ${minWeight}–${maxWeight} g`);
      return;
    }
    if (!qty || qty <= 0) {
      setError("Shipment quantity must be > 0");
      return;
    }

    setSubmitting(true);
    try {
      const result = await api.createSimulation({
        tea_density: density,
        package_weight: weight,
        shipment_quantity: qty,
        shipment_type: form.shipment_type as "total_weight" | "per_container",
        package_shape: form.package_shape as "square" | "round",
        packaging_material: form.packaging_material as "paper" | "plastic" | "metal",
        target_market: form.target_market || undefined,
        pallet_type: form.pallet_type,
      });
      router.push(`/results/${result.id}`);
    } catch (e: any) {
      setError(e.message || "Optimization failed. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">New Simulation</h1>
        <p className="text-muted-foreground mt-1">
          Enter packaging parameters and let AI optimize your supply chain.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FlaskConical className="h-5 w-5 text-primary" />
              Input Parameters
            </CardTitle>
            <CardDescription>
              Provide tea density, package weight, and shipment details.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/50 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="density">Tea Density (g/cm³)</Label>
                <Input
                  id="density"
                  type="number"
                  step="0.01"
                  min={minDensity}
                  max={maxDensity}
                  value={form.tea_density}
                  onChange={(e) => update("tea_density", e.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  {ref?.tea_densities.length
                    ? ref.tea_densities
                        .slice(0, 2)
                        .map((d) => `${d.tea_type.replace(/_/g, " ")} ${d.min_density}–${d.max_density}`)
                        .join(", ")
                    : "Typical: black 0.30–0.42, green 0.28–0.38"}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="weight">Package Weight</Label>
                {/* A dropdown of real SKUs, per the brief. Options are served from
                    the package_weight_refs table rather than hardcoded here, so
                    the catalogue stays revisable without a redeploy. */}
                <Select
                  id="weight"
                  options={weightOptions}
                  value={form.package_weight}
                  onChange={(e) => update("package_weight", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Net tea per pouch</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="qty">Shipment Quantity (units)</Label>
                <Input
                  id="qty"
                  type="number"
                  min="1"
                  value={form.shipment_quantity}
                  onChange={(e) => update("shipment_quantity", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="shipmentType">Shipment Type</Label>
                <Select
                  id="shipmentType"
                  options={SHIPMENT_TYPE_OPTIONS}
                  value={form.shipment_type}
                  onChange={(e) => update("shipment_type", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {form.shipment_type === "per_container"
                    ? "Must fit in a single container"
                    : "Uses as many containers as needed"}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="shape">Package Shape</Label>
                <Select
                  id="shape"
                  options={shapeOptions}
                  value={form.package_shape}
                  onChange={(e) => update("package_shape", e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="material">Packaging Material</Label>
                <Select
                  id="material"
                  options={materialOptions}
                  value={form.packaging_material}
                  onChange={(e) => update("packaging_material", e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="pallet">Pallet Type</Label>
              <Select
                id="pallet"
                options={palletOptions}
                value={form.pallet_type}
                onChange={(e) => update("pallet_type", e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                The pallet your warehouse ships on. The whole optimization — and
                the baseline it is compared against — is solved on this pallet.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="market">
                Target Market <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="market"
                placeholder="e.g. EU, US, Middle East"
                value={form.target_market}
                onChange={(e) => update("target_market", e.target.value)}
              />
            </div>

            <div className="pt-4">
              <Button type="submit" size="lg" className="w-full" disabled={submitting}>
                {submitting ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Running Optimization…
                  </>
                ) : (
                  "Run Optimization"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
