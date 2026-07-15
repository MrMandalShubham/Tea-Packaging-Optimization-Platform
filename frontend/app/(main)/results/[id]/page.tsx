"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, SimulationDetail, AIAnalysis } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Spinner } from "@/components/ui/spinner";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { ChatWidget } from "@/components/layout/chat-widget";
import { ArrowLeft, Package, Truck, DollarSign, TrendingDown, Printer, Brain, Sparkles } from "lucide-react";

// ── Helpers ──────────────────────────────────────────────────────────────────

const CONTAINER_COLORS = {
  "20GP": "#22c55e",
  "40GP": "#3b82f6",
  "40HC": "#8b5cf6",
};

const PIE_COLORS = ["#22c55e", "#3b82f6", "#f59e0b"];

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

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<SimulationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<AIAnalysis | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    if (!params.id) return;
    api
      .getSimulation(params.id)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  async function runAIAnalysis() {
    if (!params.id) return;
    setAiLoading(true);
    try {
      const result = await api.getAIAnalysis(params.id);
      setAi(result);
    } catch (e: any) {
      setAi({ validations: [], summary: "", error: e.message });
    } finally {
      setAiLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
        <p className="text-destructive font-medium">
          {error || "Simulation not found"}
        </p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/")}>
          <ArrowLeft className="h-4 w-4 mr-2" /> Back to Dashboard
        </Button>
      </div>
    );
  }

  const { best_package, carton, pallet, best_container, container_alternatives, comparison, inputs } = data;
  const allContainers = best_container
    ? [best_container, ...container_alternatives]
    : [];

  // Container chart data
  const containerChartData = allContainers.map((c) => ({
    name: c.container_type,
    Utilization: c.utilization_pct,
    "Empty Space (m³)": c.empty_space_m3,
    "Cartons Per Container": c.cartons_per_container,
  }));

  // Cost pie data
  const costPieData = [
    { name: "Packaging", value: comparison?.packaging_cost_ai ?? 0 },
    { name: "Freight", value: comparison?.freight_cost_ai ?? 0 },
    { name: "Savings", value: comparison?.total_savings ?? 0 },
  ].filter((d) => d.value > 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Button variant="ghost" size="sm" className="mb-2 -ml-2" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
          <h1 className="text-3xl font-bold tracking-tight">Optimization Results</h1>
          <p className="text-muted-foreground mt-1">
            {formatDate(data.created_at)}
            {inputs && (
              <span className="ml-3">
                {inputs.package_weight}g · {inputs.package_shape} · {inputs.packaging_material}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            className="no-print"
          >
            <Printer className="h-4 w-4 mr-1" /> Export PDF
          </Button>
          <Badge variant="success" className="text-base px-3 py-1">
            {data.status}
          </Badge>
        </div>
      </div>

      {/* ── AI Analysis ─────────────────────────────────────────────── */}
      {!ai && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="lg"
            onClick={runAIAnalysis}
            disabled={aiLoading}
            className="gap-2 border-purple-300 text-purple-700 hover:bg-purple-50"
          >
            {aiLoading ? (
              <><Spinner size="sm" /> Analyzing with AI…</>
            ) : (
              <><Brain className="h-5 w-5" /> Analyze with AI</>
            )}
          </Button>
        </div>
      )}

      {ai && !ai.error && (
        <>
          {/* Validation badges */}
          <div className="flex flex-wrap gap-2">
            {ai.validations.map((v) => (
              <Badge
                key={v.stage}
                variant={v.status === "valid" ? "success" : v.status === "warning" ? "warning" : "destructive"}
                className="gap-1 capitalize"
              >
                {v.status === "valid" ? "✅" : v.status === "warning" ? "⚠️" : "❌"} {v.stage}
              </Badge>
            ))}
          </div>

          {/* AI Summary */}
          {ai.summary && (
            <Card className="border-purple-200 bg-purple-50/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2 text-purple-800">
                  <Sparkles className="h-4 w-4" /> AI Analysis
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-purple-900 whitespace-pre-line leading-relaxed">{ai.summary}</p>
              </CardContent>
            </Card>
          )}

          {/* Per-stage validation detail */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {ai.validations.filter(v => v.message).map((v) => (
              <Card key={v.stage} className="text-xs">
                <CardContent className="p-3 space-y-1">
                  <p className="font-semibold capitalize flex items-center gap-1">
                    {v.status === "valid" ? "✅" : v.status === "warning" ? "⚠️" : "❌"} {v.stage}
                  </p>
                  <p className="text-muted-foreground">{v.message}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {ai?.error && (
        <div className="rounded-md bg-destructive/10 border border-destructive/30 p-3 text-sm text-destructive text-center">
          AI analysis unavailable: {ai.error}
          <Button variant="ghost" size="sm" className="ml-2" onClick={() => setAi(null)}>Retry</Button>
        </div>
      )}

      {/* ── Best Package + Alternatives ─────────────────────────────── */}
      <div>
        <h2 className="text-xl font-semibold mb-3 flex items-center gap-2">
          <Package className="h-5 w-5 text-primary" /> Package Recommendation
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {best_package && (
            <Card className="border-primary/50 ring-1 ring-primary/20">
              <CardHeader>
                <CardTitle className="text-base">Best Package</CardTitle>
                <CardDescription>Lowest cost, optimal fill</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label="Dimensions" value={`${best_package.length_mm} × ${best_package.width_mm} × ${best_package.height_mm} mm`} />
                <Row label="Volume" value={`${best_package.volume_cm3} cm³`} />
                <Row label="Fill Ratio" value={`${(best_package.fill_ratio * 100).toFixed(1)}%`} />
                <Row label="Material" value={`${best_package.material} · ${best_package.material_usage_sqm.toFixed(3)} m²`} />
                <Row label="Cost/unit" value={`₹${best_package.cost_estimate.toFixed(3)}`} bold />
              </CardContent>
            </Card>
          )}

          {data.package_alternatives.map((alt, i) => (
            <Card key={alt.rank || i}>
              <CardHeader>
                <CardTitle className="text-base">Alternative #{i + 1}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label="Dimensions" value={`${alt.length_mm} × ${alt.width_mm} × ${alt.height_mm} mm`} />
                <Row label="Volume" value={`${alt.volume_cm3} cm³`} />
                <Row label="Fill Ratio" value={`${(alt.fill_ratio * 100).toFixed(1)}%`} />
                <Row label="Cost/unit" value={`₹${alt.cost_estimate.toFixed(3)}`} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Carton + Pallet ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {carton && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Carton Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Inner Dimensions" value={`${carton.length_mm} × ${carton.width_mm} × ${carton.height_mm} mm`} />
              <Row label="Units Per Carton" value={String(carton.units_per_carton)} bold />
              <Row label="Carton Weight" value={`${carton.carton_weight_kg} kg`} />
              <Row label="Board Grade" value={carton.board_grade} />
            </CardContent>
          </Card>
        )}

        {pallet && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pallet Layout</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Cartons Per Layer" value={String(pallet.cartons_per_layer)} />
              <Row label="Layers" value={String(pallet.layers)} />
              <Row label="Cartons Per Pallet" value={String(pallet.cartons_per_pallet)} bold />
              <Row label="Pallet Height" value={`${pallet.pallet_height_m} m`} />
              <Row label="Total Weight" value={`${pallet.total_weight_kg} kg`} />
            </CardContent>
          </Card>
        )}
      </div>

      {/* ── Container Comparison Chart ───────────────────────────────── */}
      {allContainers.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Truck className="h-5 w-5 text-primary" /> Container Comparison
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-72 mb-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={containerChartData} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis unit="%" />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, "Utilization"]}
                  />
                  <Bar dataKey="Utilization" radius={[4, 4, 0, 0]}>
                    {containerChartData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={CONTAINER_COLORS[entry.name as keyof typeof CONTAINER_COLORS] || "#22c55e"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Container detail table */}
            <div className="border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Container</TableHead>
                    <TableHead className="text-right">Cartons</TableHead>
                    <TableHead className="text-right">Units</TableHead>
                    <TableHead className="text-right">Utilization</TableHead>
                    <TableHead className="text-right">Freight Cost</TableHead>
                    <TableHead>Best</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allContainers.map((c) => (
                    <TableRow key={c.container_type} className={c.is_best ? "bg-primary/5" : ""}>
                      <TableCell className="font-medium">{c.container_type}</TableCell>
                      <TableCell className="text-right">{c.cartons_per_container}</TableCell>
                      <TableCell className="text-right">{c.total_units.toLocaleString()}</TableCell>
                      <TableCell className="text-right">{c.utilization_pct}%</TableCell>
                      <TableCell className="text-right">{formatCurrency(c.freight_cost)}</TableCell>
                      <TableCell>{c.is_best && <Badge variant="success">Best</Badge>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Cost Breakdown + Comparison ──────────────────────────────── */}
      {comparison && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Cost pie */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <DollarSign className="h-5 w-5 text-primary" /> Cost Breakdown
              </CardTitle>
            </CardHeader>
            <CardContent>
              {costPieData.length > 0 ? (
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={costPieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={90}
                        paddingAngle={4}
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${formatCurrency(value)}`}
                      >
                        {costPieData.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v: number) => formatCurrency(v)} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No cost data available.</p>
              )}
              <div className="mt-3 space-y-1 text-sm">
                <Row label="AI Total Cost" value={formatCurrency(comparison.total_cost_ai)} bold />
                <Row label="AI Savings" value={
                  <span className="text-success font-medium">{formatCurrency(comparison.total_savings)}</span>
                } />
              </div>
            </CardContent>
          </Card>

          {/* Comparison table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <TrendingDown className="h-5 w-5 text-primary" /> Current vs AI
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="border rounded-md">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Parameter</TableHead>
                      <TableHead className="text-right">Current</TableHead>
                      <TableHead className="text-right">AI</TableHead>
                      <TableHead className="text-right">Δ</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {comparison.rows.map((row) => (
                      <TableRow key={row.parameter_name}>
                        <TableCell className="text-xs">{row.parameter_name}</TableCell>
                        <TableCell className="text-right text-xs">{row.current_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs font-medium">{row.ai_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs">
                          <span className={row.improvement_pct > 0 ? "text-success" : "text-destructive"}>
                            {formatPct(row.improvement_pct)}
                          </span>
                        </TableCell>
                      </TableRow>
                    ))}
                    <TableRow className="border-t-2">
                      <TableCell className="font-semibold text-xs">Total Cost</TableCell>
                      <TableCell className="text-right text-xs">{formatCurrency(comparison.total_cost_current)}</TableCell>
                      <TableCell className="text-right text-xs font-bold">{formatCurrency(comparison.total_cost_ai)}</TableCell>
                      <TableCell className="text-right">
                        <Badge variant="success" className="text-xs">
                          Save {formatCurrency(comparison.total_savings)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      <ChatWidget
        contextText={
          data
            ? `Tea density: ${data.inputs?.tea_density} g/cm³. Package weight: ${data.inputs?.package_weight}g. Shipment: ${data.inputs?.shipment_quantity} units. Best package: ${data.best_package?.length_mm}×${data.best_package?.width_mm}×${data.best_package?.height_mm}mm, ${data.best_package?.volume_cm3} cm³, ${data.best_package?.material}. Carton: ${data.carton?.units_per_carton} units, ${data.carton?.carton_weight_kg}kg, ${data.carton?.board_grade}. Pallet: ${data.pallet?.cartons_per_pallet} cartons. Container: ${data.best_container?.container_type}, ${data.best_container?.utilization_pct}% utilization, ${data.best_container?.containers_needed} needed. Total cost: ₹${data.comparison?.total_cost_ai?.toLocaleString()}. Total savings: ₹${data.comparison?.total_savings?.toLocaleString()}.`
            : ""
        }
      />
    </div>
  );
}

// ── Inline row helper ────────────────────────────────────────────────────────

function Row({
  label,
  value,
  bold,
}: {
  label: string;
  value: React.ReactNode;
  bold?: boolean;
}) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-muted-foreground">{label}</span>
      <span className={bold ? "font-semibold" : ""}>{value}</span>
    </div>
  );
}
