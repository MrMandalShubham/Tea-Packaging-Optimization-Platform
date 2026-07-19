"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, PaginatedSimulations, SimulationListItem } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ChevronLeft, ChevronRight, History as HistoryIcon } from "lucide-react";

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

export default function HistoryPage() {
  const router = useRouter();
  const [data, setData] = useState<PaginatedSimulations | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    api
      .listSimulations(page, 20)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Simulation History</h1>
        <p className="text-muted-foreground mt-1">
          Review all your past optimization runs.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <Spinner size="lg" />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
          <p className="text-destructive font-medium">Failed to load</p>
          <p className="text-sm text-muted-foreground mt-1">{error}</p>
        </div>
      ) : data && data.items.length > 0 ? (
        <>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Density</TableHead>
                  <TableHead>Weight (g)</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead className="text-right">Total Cost</TableHead>
                  <TableHead className="text-right">Savings</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((sim) => (
                  <TableRow
                    key={sim.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => router.push(`/results/${sim.id}`)}
                  >
                    <TableCell className="font-medium">{formatDate(sim.created_at)}</TableCell>
                    <TableCell>{sim.tea_density ?? "—"}</TableCell>
                    <TableCell>{sim.package_weight ?? "—"}</TableCell>
                    <TableCell>{sim.shipment_quantity?.toLocaleString() ?? "—"}</TableCell>
                    <TableCell className="text-right">
                      {sim.total_cost != null ? formatCurrency(sim.total_cost) : "—"}
                    </TableCell>
                    <TableCell className="text-right text-success font-medium">
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

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * 20 + 1}–{Math.min(page * 20, data.total)} of {data.total}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed bg-card px-6 py-16 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
            <HistoryIcon className="h-7 w-7" aria-hidden />
          </span>
          <div className="max-w-md space-y-1.5">
            <h2 className="text-lg font-semibold">Nothing here yet</h2>
            <p className="text-sm text-muted-foreground">
              Every optimization you run is saved here with its full results, so
              you can revisit, compare and export past plans.
            </p>
          </div>
          <Button onClick={() => router.push("/simulation")}>
            Run your first simulation
          </Button>
        </div>
      )}
    </div>
  );
}
