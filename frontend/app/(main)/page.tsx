"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, DashboardData } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { LayoutDashboard, TrendingUp, Package, FlaskConical, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

function formatCurrency(val: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(val);
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getDashboard()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
        <p className="text-destructive font-medium">Failed to load dashboard</p>
        <p className="text-sm text-muted-foreground mt-1">{error}</p>
      </div>
    );
  }

  // First-run experience: a page of zero-tiles reads as "broken", not "new".
  // Lead the empty account to its first simulation instead.
  if (data && data.total_simulations === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">AI-powered packaging optimization overview.</p>
        </div>
        <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed bg-card px-6 py-16 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FlaskConical className="h-7 w-7" aria-hidden />
          </span>
          <div className="max-w-md space-y-1.5">
            <h2 className="text-lg font-semibold">Run your first optimization</h2>
            <p className="text-sm text-muted-foreground">
              Enter tea density, pouch weight and shipment size — the optimizer
              searches every pouch, carton, pallet and container combination and
              returns the cheapest plan that can actually be loaded.
            </p>
          </div>
          <Button onClick={() => router.push("/simulation")} className="gap-1.5">
            New Simulation <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">AI-powered packaging optimization overview.</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Simulations
            </CardTitle>
            <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{data?.total_simulations ?? 0}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Savings
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-success" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-success">
              {data ? formatCurrency(data.total_savings) : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Avg Container Utilization
            </CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {data ? `${data.average_container_utilization}%` : "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent simulations */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Recent Simulations</h2>
        {data && data.recent_simulations.length > 0 ? (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Density</TableHead>
                  <TableHead>Weight</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead className="text-right">Total Cost</TableHead>
                  <TableHead className="text-right">Savings</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recent_simulations.map((sim) => (
                  <TableRow
                    key={sim.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => router.push(`/results/${sim.id}`)}
                  >
                    <TableCell className="font-medium">{formatDate(sim.created_at)}</TableCell>
                    <TableCell>{sim.tea_density ?? "—"} g/cm³</TableCell>
                    <TableCell>{sim.package_weight ?? "—"} g</TableCell>
                    <TableCell>{sim.shipment_quantity?.toLocaleString() ?? "—"}</TableCell>
                    <TableCell className="text-right">
                      {sim.total_cost != null ? formatCurrency(sim.total_cost) : "—"}
                    </TableCell>
                    <TableCell className="text-right text-success">
                      {sim.total_savings != null ? formatCurrency(sim.total_savings) : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={sim.status === "completed" ? "success" : "secondary"}>
                        {sim.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="rounded-lg border bg-card p-8 text-center">
            <p className="text-muted-foreground">
              No simulations yet.{" "}
              <a href="/simulation" className="text-primary underline">
                Create your first simulation
              </a>
              .
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
