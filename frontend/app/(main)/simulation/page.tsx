"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { FlaskConical } from "lucide-react";

const SHAPE_OPTIONS = [
  { value: "square", label: "Square / Rectangular" },
  { value: "round", label: "Round / Cylindrical" },
];

const MATERIAL_OPTIONS = [
  { value: "paper", label: "Paper / Kraft" },
  { value: "plastic", label: "Plastic / LDPE" },
  { value: "metal", label: "Metal / Foil Laminate" },
];

export default function NewSimulationPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    tea_density: "0.35",
    package_weight: "250",
    shipment_quantity: "100000",
    package_shape: "square",
    packaging_material: "paper",
    target_market: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    if (!density || density <= 0 || density > 5) {
      setError("Tea density must be between 0–5 g/cm³");
      return;
    }
    if (!weight || weight <= 0 || weight > 500) {
      setError("Package weight must be between 1–500 g");
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
        shipment_type: "total_weight",
        package_shape: form.package_shape as "square" | "round",
        packaging_material: form.packaging_material as "paper" | "plastic" | "metal",
        target_market: form.target_market || undefined,
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
                  min="0.1"
                  max="5"
                  value={form.tea_density}
                  onChange={(e) => update("tea_density", e.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Typical: black 0.30–0.42, green 0.28–0.38
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="weight">Package Weight (g)</Label>
                <Input
                  id="weight"
                  type="number"
                  step="1"
                  min="1"
                  max="500"
                  value={form.package_weight}
                  onChange={(e) => update("package_weight", e.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">e.g. 250g, 500g pouch</p>
              </div>
            </div>

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

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="shape">Package Shape</Label>
                <Select
                  id="shape"
                  options={SHAPE_OPTIONS}
                  value={form.package_shape}
                  onChange={(e) => update("package_shape", e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="material">Packaging Material</Label>
                <Select
                  id="material"
                  options={MATERIAL_OPTIONS}
                  value={form.packaging_material}
                  onChange={(e) => update("packaging_material", e.target.value)}
                />
              </div>
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
