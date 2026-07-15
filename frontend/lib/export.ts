/**
 * Export a simulation to Excel.
 *
 * Runs entirely client-side: the data is already loaded in the page, so shipping
 * it back to the server only to receive a file would add a round trip and a new
 * endpoint for no benefit.
 *
 * The workbook mirrors what the Results page shows, plus the baseline assumptions —
 * a spreadsheet of savings with no statement of what they are measured against is
 * exactly the sort of unfalsifiable claim this project set out to avoid.
 */

import type { SimulationDetail } from "@/lib/api";

/** Column widths in characters, applied per sheet. */
function widths(...w: number[]) {
  return w.map((wch) => ({ wch }));
}

function fmtDims(l?: number | null, w?: number | null, h?: number | null): string {
  if (l == null || w == null || h == null) return "—";
  return `${l} × ${w} × ${h} mm`;
}

export async function exportSimulationToExcel(d: SimulationDetail): Promise<void> {
  // Imported lazily so the ~400 KB SheetJS bundle is fetched only when someone
  // actually clicks Export, rather than on every page load.
  const XLSX = await import("xlsx");

  const wb = XLSX.utils.book_new();
  const created = new Date(d.created_at).toLocaleString();

  // ── Summary ──────────────────────────────────────────────────────────────
  const i = d.inputs;
  const bc = d.best_container;
  const cmp = d.comparison;

  const summary: (string | number)[][] = [
    ["Tea Packaging Optimization — Summary"],
    ["Simulation ID", d.id],
    ["Created", created],
    [],
    ["INPUTS"],
    ["Tea density", i ? `${i.tea_density} g/cm³` : "—"],
    ["Package weight", i ? `${i.package_weight} g` : "—"],
    ["Shipment quantity", i ? i.shipment_quantity : "—"],
    ["Shipment type", i?.shipment_type ?? "—"],
    ["Package shape", i?.package_shape ?? "—"],
    ["Packaging material", i?.packaging_material ?? "—"],
    ["Target market", i?.target_market || "—"],
    [],
    ["RECOMMENDATION"],
    [
      "Pouch",
      fmtDims(d.best_package?.length_mm, d.best_package?.width_mm, d.best_package?.height_mm),
    ],
    ["Fill ratio", d.best_package ? `${(d.best_package.fill_ratio * 100).toFixed(1)}%` : "—"],
    ["Carton (outer)", fmtDims(d.carton?.length_mm, d.carton?.width_mm, d.carton?.height_mm)],
    ["Units per carton", d.carton?.units_per_carton ?? "—"],
    ["Carton weight", d.carton ? `${d.carton.carton_weight_kg} kg` : "—"],
    ["Board grade", d.carton?.board_grade ?? "—"],
    ["Cartons per pallet", d.pallet?.cartons_per_pallet ?? "—"],
    ["Pallet height", d.pallet ? `${d.pallet.pallet_height_m} m` : "—"],
    ["Container", bc?.container_type ?? "—"],
    ["Containers needed", bc?.containers_needed ?? "—"],
    ["Container utilisation", bc ? `${bc.utilization_pct}%` : "—"],
    ["Pallets stacked", bc?.pallet_stack ?? "—"],
    [],
    ["COST"],
    ["Current practice", cmp?.total_cost_current ?? 0],
    ["Optimised", cmp?.total_cost_ai ?? 0],
    ["Saving", cmp?.total_savings ?? 0],
    [
      "Saving %",
      cmp && cmp.total_cost_current
        ? `${((cmp.total_savings / cmp.total_cost_current) * 100).toFixed(1)}%`
        : "—",
    ],
  ];
  const wsSummary = XLSX.utils.aoa_to_sheet(summary);
  wsSummary["!cols"] = widths(26, 34);
  XLSX.utils.book_append_sheet(wb, wsSummary, "Summary");

  // ── Current vs AI ────────────────────────────────────────────────────────
  if (cmp?.rows?.length) {
    const rows: (string | number)[][] = [
      ["Parameter", "Current", "AI", "Change %", "Unit", "Why it changed"],
      ...cmp.rows.map((r) => [
        r.parameter_name,
        r.current_value,
        r.ai_value,
        r.improvement_pct,
        r.unit || "",
        r.driver || "",
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = widths(24, 14, 14, 10, 10, 62);
    XLSX.utils.book_append_sheet(wb, ws, "Current vs AI");
  }

  // ── Container options (Module 6) ─────────────────────────────────────────
  const containers = [...(bc ? [bc] : []), ...d.container_alternatives];
  if (containers.length) {
    const rows: (string | number)[][] = [
      [
        "Type",
        "Recommended",
        "Cartons/container",
        "Total units/container",
        "Packed %",
        "Empty space/container m³",
        "Pallets/container",
        "Pallet stack",
        "Containers needed",
        "Shipment utilisation %",
        "Empty space total m³",
        "Freight ₹",
      ],
      ...containers.map((c) => [
        c.container_type,
        c.is_best ? "YES" : "",
        c.cartons_per_container,
        c.units_per_container,
        c.capacity_utilization_pct,
        c.empty_space_per_container_m3,
        c.pallets_per_container ?? "—",
        c.pallet_stack ?? "—",
        c.containers_needed,
        c.utilization_pct,
        c.empty_space_total_m3,
        c.freight_cost,
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = widths(10, 13, 18, 20, 11, 24, 18, 13, 18, 22, 20, 14);
    XLSX.utils.book_append_sheet(wb, ws, "Container Options");
  }

  // ── Package alternatives ─────────────────────────────────────────────────
  const packages = [...(d.best_package ? [d.best_package] : []), ...d.package_alternatives];
  if (packages.length) {
    const rows: (string | number)[][] = [
      ["Rank", "Best", "Length mm", "Width mm", "Height mm", "Volume cm³", "Fill ratio", "Cost ₹/unit"],
      ...packages.map((p) => [
        p.rank,
        p.is_best ? "YES" : "",
        p.length_mm,
        p.width_mm,
        p.height_mm,
        p.volume_cm3,
        p.fill_ratio,
        p.cost_estimate,
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    ws["!cols"] = widths(7, 7, 11, 11, 11, 12, 11, 12);
    XLSX.utils.book_append_sheet(wb, ws, "Package Options");
  }

  // ── Baseline assumptions ─────────────────────────────────────────────────
  const assumptionRows: (string | number)[][] = [
    ["How 'Current Practice' was determined"],
    [],
    [
      cmp?.baseline_is_user_supplied
        ? "These figures were supplied by you and used as-is."
        : "No current figures were supplied, so conventional practice was modelled as follows:",
    ],
    [],
    ...(cmp?.baseline_assumptions?.length
      ? cmp.baseline_assumptions.map((a) => [a])
      : [["—"]]),
    [],
    ["Both sides are costed with the same physics and the same rates."],
    ["Cost rates are indicative placeholders — see docs/assumptions.md §4."],
  ];
  const wsA = XLSX.utils.aoa_to_sheet(assumptionRows);
  wsA["!cols"] = widths(110);
  XLSX.utils.book_append_sheet(wb, wsA, "Basis of Comparison");

  const stamp = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, `tea-packaging-${d.id.slice(0, 8)}-${stamp}.xlsx`);
}
