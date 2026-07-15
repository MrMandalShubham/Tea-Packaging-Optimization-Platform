"use client";

import { useState } from "react";
import { api, CompareResponse } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Spinner } from "@/components/ui/spinner";
import { GitCompare, TrendingDown, Printer } from "lucide-react";

function formatCurrency(val: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(val);
}

function formatPct(val: number) {
  return `${val > 0 ? "+" : ""}${val.toFixed(1)}%`;
}

export default function ComparePage() {
  const [form, setForm] = useState({
    tea_density: "0.35",
    package_weight: "250",
    ship_quantity: "100000",
    current_package_length_mm: "",
    current_package_width_mm: "",
    current_package_height_mm: "",
    current_units_per_carton: "",
    current_cartons_per_pallet: "",
    current_containers: "",
    current_packaging_cost: "",
    current_freight_cost: "",
  });
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setError(null);
  }

  function orUndef(val: string): number | undefined {
    const n = parseFloat(val);
    return isNaN(n) || val === "" ? undefined : n;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await api.compare({
        tea_density: parseFloat(form.tea_density),
        package_weight: parseFloat(form.package_weight),
        ship_quantity: parseInt(form.ship_quantity),
        current_package_length_mm: orUndef(form.current_package_length_mm),
        current_package_width_mm: orUndef(form.current_package_width_mm),
        current_package_height_mm: orUndef(form.current_package_height_mm),
        current_units_per_carton: orUndef(form.current_units_per_carton) as number | undefined,
        current_cartons_per_pallet: orUndef(form.current_cartons_per_pallet) as number | undefined,
        current_containers: orUndef(form.current_containers) as number | undefined,
        current_packaging_cost: orUndef(form.current_packaging_cost),
        current_freight_cost: orUndef(form.current_freight_cost),
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Current vs AI Comparison</h1>
        <p className="text-muted-foreground mt-1">
          See how AI optimization improves over your current packaging.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitCompare className="h-5 w-5 text-primary" />
              Input Parameters
            </CardTitle>
            <CardDescription>
              Required: tea density, weight, quantity. Optional: current values (auto-estimated if blank).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/50 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* Required fields */}
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="density">Tea Density (g/cm³)</Label>
                <Input
                  id="density"
                  type="number"
                  step="0.01"
                  value={form.tea_density}
                  onChange={(e) => update("tea_density", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="weight">Package Weight (g)</Label>
                <Input
                  id="weight"
                  type="number"
                  value={form.package_weight}
                  onChange={(e) => update("package_weight", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="qty">Shipment Qty</Label>
                <Input
                  id="qty"
                  type="number"
                  value={form.ship_quantity}
                  onChange={(e) => update("ship_quantity", e.target.value)}
                  required
                />
              </div>
            </div>

            {/* Optional current values */}
            <p className="text-sm font-medium text-muted-foreground pt-2 border-t">
              Current Configuration (leave blank for auto-estimate)
            </p>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cp-l">Package L (mm)</Label>
                <Input id="cp-l" type="number" value={form.current_package_length_mm} onChange={(e) => update("current_package_length_mm", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cp-w">Package W (mm)</Label>
                <Input id="cp-w" type="number" value={form.current_package_width_mm} onChange={(e) => update("current_package_width_mm", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cp-h">Package H (mm)</Label>
                <Input id="cp-h" type="number" value={form.current_package_height_mm} onChange={(e) => update("current_package_height_mm", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cc-u">Units/Carton</Label>
                <Input id="cc-u" type="number" value={form.current_units_per_carton} onChange={(e) => update("current_units_per_carton", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cc-p">Cartons/Pallet</Label>
                <Input id="cc-p" type="number" value={form.current_cartons_per_pallet} onChange={(e) => update("current_cartons_per_pallet", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cc-c">Containers</Label>
                <Input id="cc-c" type="number" value={form.current_containers} onChange={(e) => update("current_containers", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cc-pc">Packaging Cost (₹)</Label>
                <Input id="cc-pc" type="number" value={form.current_packaging_cost} onChange={(e) => update("current_packaging_cost", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cc-fc">Freight Cost (₹)</Label>
                <Input id="cc-fc" type="number" value={form.current_freight_cost} onChange={(e) => update("current_freight_cost", e.target.value)} />
              </div>
            </div>

            <Button type="submit" size="lg" className="w-full" disabled={loading}>
              {loading ? <><Spinner size="sm" className="mr-2" /> Comparing…</> : "Run Comparison"}
            </Button>
          </CardContent>
        </Card>
      </form>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Savings banner */}
          <Card className="border-success/50 bg-success/5">
            <CardContent className="py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <TrendingDown className="h-6 w-6 text-success" />
                <div>
                  <p className="font-semibold text-success">AI Optimization Savings</p>
                  <p className="text-sm text-muted-foreground">
                    {formatCurrency(result.total_savings)} saved — {result.total_cost_current > 0
                      ? `${((result.total_savings / result.total_cost_current) * 100).toFixed(1)}% reduction`
                      : "N/A"}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.print()}
                className="no-print"
              >
                <Printer className="h-4 w-4 mr-1" /> Export PDF
              </Button>
            </CardContent>
          </Card>

          {/* Comparison table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Current vs AI — Detailed Comparison</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="border rounded-md overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Parameter</TableHead>
                      <TableHead className="text-right">Current</TableHead>
                      <TableHead className="text-right">AI Optimized</TableHead>
                      <TableHead className="text-right w-24">Improvement</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.rows.map((row) => (
                      <TableRow key={row.parameter_name}>
                        <TableCell className="text-xs font-medium">{row.parameter_name}</TableCell>
                        <TableCell className="text-right text-xs">{row.current_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs">{row.ai_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs">
                          <Badge
                            variant={row.improvement_pct > 0 ? "success" : row.improvement_pct < 0 ? "destructive" : "secondary"}
                          >
                            {formatPct(row.improvement_pct)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Cost summary rows */}
              <div className="mt-4 grid grid-cols-3 gap-4">
                <CostBox label="Current Total" value={result.total_cost_current} variant="muted" />
                <CostBox label="AI Total" value={result.total_cost_ai} variant="primary" />
                <CostBox label="Savings" value={result.total_savings} variant="success" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function CostBox({
  label,
  value,
  variant,
}: {
  label: string;
  value: number;
  variant: "muted" | "primary" | "success";
}) {
  const colors = {
    muted: "bg-muted text-muted-foreground",
    primary: "bg-primary/10 text-primary",
    success: "bg-success/10 text-success",
  };
  return (
    <div className={`rounded-lg p-4 text-center ${colors[variant]}`}>
      <p className="text-xs font-medium">{label}</p>
      <p className="text-lg font-bold mt-1">{formatCurrency(value)}</p>
    </div>
  );
}
