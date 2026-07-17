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
import { Container3DPanel } from "@/components/viz/container-3d-panel";
import { MaxCapacityPanel } from "@/components/viz/max-capacity-panel";
import { exportSimulationToExcel } from "@/lib/export";
import {
  ArrowLeft,
  Package,
  Truck,
  DollarSign,
  TrendingDown,
  Printer,
  Brain,
  Sparkles,
  FileSpreadsheet,
  Info,
} from "lucide-react";

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

  // Container chart — packing density, which compares the schemes like for like.
  // Shipment utilisation would rank them by how full the last box happens to be.
  const containerChartData = allContainers.map((c) => ({
    name: c.container_type,
    Utilization: c.capacity_utilization_pct,
  }));

  // Cost breakdown. Savings is deliberately excluded: it is the difference
  // between two totals, not a slice of this one, and putting it in the same pie
  // as real costs makes the total meaningless.
  const costPieData = [
    { name: "Packaging", value: comparison?.packaging_cost_ai ?? 0 },
    { name: "Carton board", value: comparison?.carton_cost_ai ?? 0 },
    { name: "Freight", value: comparison?.freight_cost_ai ?? 0 },
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
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportSimulationToExcel(data)}
            className="no-print"
          >
            <FileSpreadsheet className="h-4 w-4 mr-1" /> Excel
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            className="no-print"
            title="Opens your browser's print dialog — choose 'Save as PDF'"
          >
            <Printer className="h-4 w-4 mr-1" /> PDF
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
                <AiBrief text={ai.summary} />
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
        {/* An alternative often shows a LOWER cost/unit than the recommendation —
            a cube minimises pouch material but tiles the carton and pallet badly,
            losing far more on freight than it saves on film. Ranking is by total
            landed cost, so say that plainly rather than letting the table look
            self-contradictory. */}
        <p className="text-sm text-muted-foreground mb-3 -mt-1">
          Ranked by total landed cost — pouch + carton board + freight. A pouch with
          a lower cost per unit can still lose overall if it stacks poorly.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {best_package && (
            <Card className="border-primary/50 ring-1 ring-primary/20">
              <CardHeader>
                <CardTitle className="text-base">Recommended</CardTitle>
                <CardDescription>Lowest total landed cost</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label="Dimensions" value={`${best_package.length_mm} × ${best_package.width_mm} × ${best_package.height_mm} mm`} />
                {/* Product volume is the tea itself (mass / density); pouch volume
                    adds headspace. Showing only one of them invites the reader to
                    assume the pouch is 100% tea. */}
                <Row label="Product Volume" value={`${best_package.product_volume_cm3} cm³`} />
                <Row label="Pouch Volume" value={`${best_package.volume_cm3} cm³`} />
                <Row
                  label="Headspace"
                  value={`${(best_package.volume_cm3 - best_package.product_volume_cm3).toFixed(1)} cm³`}
                />
                <Row label="Fill Ratio" value={`${(best_package.fill_ratio * 100).toFixed(1)}%`} />
                <Row label="Material Usage" value={`${best_package.material} · ${best_package.material_usage_cm2.toFixed(1)} cm²`} />
                <Row label="Estimated Cost" value={`₹${best_package.cost_estimate.toFixed(3)} / unit`} bold />
              </CardContent>
            </Card>
          )}

          {data.package_alternatives.map((alt, i) => (
            <Card key={alt.rank || i}>
              <CardHeader>
                <CardTitle className="text-base">Alternative #{i + 1}</CardTitle>
                <CardDescription>
                  {alt.cost_estimate < (best_package?.cost_estimate ?? Infinity)
                    ? "Cheaper film, worse overall"
                    : "Higher total cost"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Row label="Dimensions" value={`${alt.length_mm} × ${alt.width_mm} × ${alt.height_mm} mm`} />
                <Row label="Pouch Volume" value={`${alt.volume_cm3} cm³`} />
                <Row label="Fill Ratio" value={`${(alt.fill_ratio * 100).toFixed(1)}%`} />
                <Row label="Estimated Cost" value={`₹${alt.cost_estimate.toFixed(3)} / unit`} />
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
              {/* Outer is the spec you order and palletise; inner is the cavity
                  the pouches sit in. This card previously labelled the outer
                  dimensions "Inner". */}
              <Row label="Outer Dimensions" value={`${carton.length_mm} × ${carton.width_mm} × ${carton.height_mm} mm`} bold />
              <Row label="Inner Dimensions" value={`${carton.inner_length_mm} × ${carton.inner_width_mm} × ${carton.inner_height_mm} mm`} />
              <Row label="Units Per Carton" value={`${carton.units_per_carton}${carton.arrangement ? ` (${carton.arrangement})` : ""}`} bold />
              <Row label="Carton Weight" value={`${carton.carton_weight_kg} kg`} />
              <Row label="Board Grade" value={carton.board_grade} />
              {carton.board_cost_per_carton != null && (
                <Row label="Board Cost" value={`₹${carton.board_cost_per_carton.toFixed(2)} / carton`} />
              )}
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
              {pallet.footprint_utilization_pct != null && (
                <Row label="Footprint Used" value={`${pallet.footprint_utilization_pct}%`} />
              )}
              {pallet.layer_pattern && <Row label="Layer Pattern" value={pallet.layer_pattern} />}
              {best_container?.pallet_stack != null && (
                <Row
                  label="Stacked In Container"
                  value={best_container.pallet_stack > 1 ? `${best_container.pallet_stack} high` : "Floor only"}
                />
              )}
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
                {/* Every column states which container it describes. A single
                    "Units" column once meant capacity across all containers,
                    which made a 20GP look like it out-shipped a 40GP — it
                    doesn't, it just needs five boxes instead of two. */}
                <TableHeader>
                  <TableRow>
                    <TableHead rowSpan={2} className="align-bottom">Container</TableHead>
                    <TableHead colSpan={4} className="text-center border-l text-xs">
                      Per container (full load)
                    </TableHead>
                    <TableHead colSpan={3} className="text-center border-l text-xs">
                      This shipment
                    </TableHead>
                    <TableHead rowSpan={2} className="align-bottom border-l">Best</TableHead>
                  </TableRow>
                  <TableRow>
                    <TableHead className="text-right border-l">Cartons</TableHead>
                    <TableHead className="text-right" title="Pouches in one full container">
                      Total Units
                    </TableHead>
                    <TableHead className="text-right" title="Packing density of a full container">
                      Packed
                    </TableHead>
                    <TableHead className="text-right" title="Unused volume in one full container">
                      Empty Space
                    </TableHead>
                    <TableHead className="text-right border-l">Needed</TableHead>
                    <TableHead className="text-right" title="Share of booked volume that holds tea">
                      Utilization
                    </TableHead>
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
                      <TableCell className="text-right border-l">{c.cartons_per_container.toLocaleString()}</TableCell>
                      <TableCell className="text-right">{c.units_per_container.toLocaleString()}</TableCell>
                      <TableCell className="text-right">{c.capacity_utilization_pct}%</TableCell>
                      <TableCell className="text-right">{c.empty_space_per_container_m3} m³</TableCell>
                      <TableCell className="text-right border-l font-medium">{c.containers_needed}</TableCell>
                      <TableCell className="text-right">{c.utilization_pct}%</TableCell>
                      <TableCell className="text-right">{formatCurrency(c.freight_cost)}</TableCell>
                      <TableCell className="border-l">{c.is_best && <Badge variant="success">Best</Badge>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Maximum capacity ─────────────────────────────────────────── */}
      {/* Sits right after Container Comparison: it answers "how much fits in one
          container", so it belongs next to the container numbers it extends. */}
      <MaxCapacityPanel simulationId={data.id} />

      {/* ── 3D load plan ─────────────────────────────────────────────── */}
      <Container3DPanel simulationId={data.id} />

      {/* ── Cost Breakdown + Comparison ──────────────────────────────── */}
      {/* The comparison table carries a driver sentence per row, so it gets two
          thirds of the width. At half width the explanations wrapped to two words
          a line and became unreadable — which defeats the point of writing them. */}
      {comparison && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Cost pie */}
          <Card className="md:col-span-1">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <DollarSign className="h-5 w-5 text-primary" /> Cost Breakdown
              </CardTitle>
            </CardHeader>
            <CardContent>
              {costPieData.length > 0 ? (
                <>
                  {/* Labels were drawn outside the slices and clipped by the card
                      on both sides. The values are listed underneath instead,
                      where they are legible and can't overflow. */}
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={costPieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={72}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {costPieData.map((_, i) => (
                            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => formatCurrency(v)} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="mt-2 space-y-1 text-sm">
                    {costPieData.map((d, i) => (
                      <li key={d.name} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2 text-muted-foreground">
                          <span
                            className="inline-block h-2.5 w-2.5 rounded-sm shrink-0"
                            style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                            aria-hidden="true"
                          />
                          {d.name}
                        </span>
                        <span className="tabular-nums">{formatCurrency(d.value)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No cost data available.</p>
              )}
              <div className="mt-3 space-y-1 text-sm">
                <Row label="AI Total Cost" value={formatCurrency(comparison.total_cost_ai)} bold />
                <Row
                  label="Saving vs current practice"
                  value={
                    <span
                      className={
                        comparison.total_savings >= 0
                          ? "text-success font-medium"
                          : "text-destructive font-medium"
                      }
                    >
                      {formatCurrency(comparison.total_savings)}
                    </span>
                  }
                />
                {comparison.total_savings < 0 && (
                  <p className="text-xs text-muted-foreground pt-1">
                    This order is too small to fill a container, so fixed freight
                    is paid either way and packaging changes cannot recover it.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Comparison table */}
          <Card className="md:col-span-2">
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
                        <TableCell className="text-xs align-top w-1/2">
                          <span className="font-medium">{row.parameter_name}</span>
                          {row.driver && (
                            // The brief asks for optimisation logic that is
                            // "transparent and explainable". A bare percentage is
                            // neither, so each row states why it moved.
                            <span className="block text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                              {row.driver}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-right text-xs align-top">{row.current_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs font-medium align-top">{row.ai_value.toFixed(1)}</TableCell>
                        <TableCell className="text-right text-xs align-top">
                          <span
                            className={
                              row.improvement_pct > 0
                                ? "text-success"
                                : row.improvement_pct < 0
                                ? "text-muted-foreground"
                                : ""
                            }
                          >
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
                        <Badge
                          variant={comparison.total_savings >= 0 ? "success" : "destructive"}
                          className="text-xs"
                        >
                          {comparison.total_savings >= 0 ? "Save " : "Costs "}
                          {formatCurrency(Math.abs(comparison.total_savings))}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>

              {/* What "Current" actually means. A savings figure with no stated
                  basis is unfalsifiable, so the basis travels with the number. */}
              <div className="mt-3 rounded-md border border-dashed bg-muted/40 p-3">
                <p className="text-xs font-medium flex items-center gap-1.5">
                  <Info className="h-3.5 w-3.5" aria-hidden="true" />
                  {comparison.baseline_is_user_supplied
                    ? "Compared against the figures you supplied"
                    : "Compared against modelled conventional practice"}
                </p>
                {comparison.baseline_assumptions.length > 0 && (
                  <ul className="mt-1.5 space-y-0.5 text-[10px] text-muted-foreground list-disc pl-4">
                    {comparison.baseline_assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                )}
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  Both sides are costed with the same physics and the same rates.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* The assistant loads its own facts from this ID server-side. */}
      <ChatWidget simulationId={data.id} />
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

// ── Minimal markdown for the AI brief ────────────────────────────────────────
// The model returns `**Heading**` lines and `- ` bullets. This renders them as
// real headings and lists instead of literal asterisks — no markdown library,
// no dangerouslySetInnerHTML, just a small line parser building React nodes.

function boldInline(text: string): React.ReactNode {
  // Split on **...** and bold the captured parts.
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      part
    )
  );
}

function AiBrief({ text }: { text: string }) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flushBullets = () => {
    if (!bullets.length) return;
    nodes.push(
      <ul key={`ul-${nodes.length}`} className="ml-1 space-y-1">
        {bullets.map((b, i) => (
          <li key={i} className="flex gap-2">
            <span aria-hidden className="mt-[2px] text-purple-400">
              •
            </span>
            <span>{boldInline(b)}</span>
          </li>
        ))}
      </ul>
    );
    bullets = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushBullets();
      continue;
    }
    // A whole-line heading: **like this**
    if (/^\*\*[^*]+\*\*$/.test(line)) {
      flushBullets();
      nodes.push(
        <p key={`h-${nodes.length}`} className="font-semibold text-purple-900 mt-3 first:mt-0">
          {line.slice(2, -2)}
        </p>
      );
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("• ")) {
      bullets.push(line.slice(2));
      continue;
    }
    flushBullets();
    nodes.push(
      <p key={`p-${nodes.length}`} className="leading-relaxed">
        {boldInline(line)}
      </p>
    );
  }
  flushBullets();

  return <div className="space-y-1.5 text-sm text-purple-900">{nodes}</div>;
}
