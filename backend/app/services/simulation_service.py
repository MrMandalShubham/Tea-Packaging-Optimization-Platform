"""
Simulation service — orchestrates the full 5-stage optimization pipeline.

Flow: Inputs → Package → Carton → Pallet → Container → Compare → Cost

Pure computation layer. Phase 3 wires this to database persistence.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.optimizers.package import optimize_package, PackageResult
from app.optimizers.carton import optimize_carton, CartonResult
from app.optimizers.pallet import optimize_pallet, estimate_current_pallet, PalletResult
from app.optimizers.container import optimize_container, ContainerResult
from app.optimizers.constants import MATERIALS, FREIGHT_RATE_PER_NM, DEFAULT_DISTANCE_NM, CONTAINERS


@dataclass
class CurrentEstimate:
    package_length_mm: float = 0
    package_width_mm: float = 0
    package_height_mm: float = 0
    carton_length_mm: float = 0
    carton_width_mm: float = 0
    carton_height_mm: float = 0
    units_per_carton: int = 0
    cartons_per_pallet: int = 0
    containers_needed: int = 0
    packaging_cost: float = 0
    freight_cost: float = 0
    total_cost: float = 0


@dataclass
class ComparisonRow:
    parameter_name: str
    current_value: float
    ai_value: float
    improvement_pct: float
    unit: str = ""


@dataclass
class PipelineResult:
    # Package stage
    best_package: Optional[PackageResult] = None
    package_alternatives: list[PackageResult] = field(default_factory=list)

    # Carton stage
    carton: Optional[CartonResult] = None

    # Pallet stage
    pallet: Optional[PalletResult] = None

    # Container stage
    best_container: Optional[ContainerResult] = None
    container_alternatives: list[ContainerResult] = field(default_factory=list)

    # Current (naive) estimate
    current: Optional[CurrentEstimate] = None

    # Comparison rows
    comparison: list[ComparisonRow] = field(default_factory=list)

    # Cost summary
    packaging_cost: float = 0.0
    freight_cost: float = 0.0
    total_cost: float = 0.0
    total_savings: float = 0.0

    # Source inputs
    tea_density: float = 0.0
    package_weight: float = 0.0
    shipment_quantity: int = 0
    shipment_type: str = ""
    package_shape: str = ""
    packaging_material: str = ""
    target_market: Optional[str] = None


def run_full_pipeline(
    tea_density: float,
    package_weight: float,
    shipment_quantity: int,
    shipment_type: str = "total_weight",
    package_shape: str = "square",
    packaging_material: str = "paper",
    target_market: Optional[str] = None,
    # Optional: user-provided current values for comparison
    current_package_l: Optional[float] = None,
    current_package_w: Optional[float] = None,
    current_package_h: Optional[float] = None,
    current_carton_l: Optional[float] = None,
    current_carton_w: Optional[float] = None,
    current_carton_h: Optional[float] = None,
    current_units_per_carton: Optional[int] = None,
    current_cartons_per_pallet: Optional[int] = None,
    current_containers: Optional[int] = None,
    current_packaging_cost: Optional[float] = None,
    current_freight_cost: Optional[float] = None,
) -> PipelineResult:
    """
    Run the complete 5-stage optimization pipeline.

    Stages:
      1. Package  — inner pouch dimensions
      2. Carton   — master carton dimensions
      3. Pallet   — pallet layout
      4. Container— container selection
      5. Compare  — current vs AI

    Returns a PipelineResult with all computed values.
    """
    # Package weight in grams → convert to kg for downstream use
    package_weight_kg = package_weight / 1000.0

    result = PipelineResult(
        tea_density=tea_density,
        package_weight=package_weight,
        shipment_quantity=shipment_quantity,
        shipment_type=shipment_type,
        package_shape=package_shape,
        packaging_material=packaging_material,
        target_market=target_market,
    )

    # ── Stage 1: Package Optimization ────────────────────────────────
    pkg_results = optimize_package(
        tea_density=tea_density,
        package_weight=package_weight,
        shape=package_shape,
        material=packaging_material,
    )
    result.best_package = pkg_results[0]
    result.package_alternatives = pkg_results[1:]

    best = result.best_package

    # ── Stage 2: Carton Optimization ─────────────────────────────────
    carton = optimize_carton(
        package_length_mm=best.length_mm,
        package_width_mm=best.width_mm,
        package_height_mm=best.height_mm,
        shipment_quantity=shipment_quantity,
        package_weight_kg=package_weight_kg,
    )
    result.carton = carton

    # ── Stage 3: Pallet Optimization ─────────────────────────────────
    pallet = optimize_pallet(
        carton_length_mm=carton.inner_length_mm,
        carton_width_mm=carton.inner_width_mm,
        carton_height_mm=carton.inner_height_mm,
        carton_weight_kg=carton.carton_weight_kg,
    )
    result.pallet = pallet

    # ── Stage 4: Container Optimization ──────────────────────────────
    containers = optimize_container(
        pallet_height_m=pallet.pallet_height_m,
        cartons_per_pallet=pallet.cartons_per_pallet,
        units_per_carton=carton.units_per_carton,
        shipment_quantity=shipment_quantity,
        carton_length_mm=carton.inner_length_mm,
        carton_width_mm=carton.inner_width_mm,
        carton_height_mm=carton.inner_height_mm,
    )
    result.best_container = containers[0]
    result.container_alternatives = containers[1:]

    bc = result.best_container

    # ── Stage 5: Current Estimate & Comparison ───────────────────────
    result.current = _compute_current_estimate(
        tea_density=tea_density,
        package_weight_kg=package_weight_kg,
        shipment_quantity=shipment_quantity,
        best=best,
        carton=carton,
        pallet=pallet,
        best_container=bc,
        packaging_material=packaging_material,
        # User overrides
        current_package_l=current_package_l,
        current_package_w=current_package_w,
        current_package_h=current_package_h,
        current_carton_l=current_carton_l,
        current_carton_w=current_carton_w,
        current_carton_h=current_carton_h,
        current_units_per_carton=current_units_per_carton,
        current_cartons_per_pallet=current_cartons_per_pallet,
        current_containers=current_containers,
        current_packaging_cost=current_packaging_cost,
        current_freight_cost=current_freight_cost,
    )

    # ── Cost Summary ────────────────────────────────────────────────
    result.packaging_cost = bc.total_units * best.cost_estimate
    result.freight_cost = bc.containers_needed * bc.freight_cost_per_container
    result.total_cost = result.packaging_cost + result.freight_cost
    result.total_savings = result.current.total_cost - result.total_cost

    # Build comparison rows
    result.comparison = _build_comparison(result)

    return result


def _compute_current_estimate(
    tea_density: float,
    package_weight_kg: float,
    shipment_quantity: int,
    best: PackageResult,
    carton: CartonResult,
    pallet: PalletResult,
    best_container: ContainerResult,
    packaging_material: str,
    current_package_l: Optional[float] = None,
    current_package_w: Optional[float] = None,
    current_package_h: Optional[float] = None,
    current_carton_l: Optional[float] = None,
    current_carton_w: Optional[float] = None,
    current_carton_h: Optional[float] = None,
    current_units_per_carton: Optional[int] = None,
    current_cartons_per_pallet: Optional[int] = None,
    current_containers: Optional[int] = None,
    current_packaging_cost: Optional[float] = None,
    current_freight_cost: Optional[float] = None,
) -> CurrentEstimate:
    """
    Build the "current" (unoptimized) estimate.

    If user provides explicit current values, use those.
    Otherwise, derive a naive estimate that's ~15-25% worse than optimized.
    """
    ce = CurrentEstimate()

    # Package — 15% larger than optimized (looser fill)
    if current_package_l:
        ce.package_length_mm = current_package_l
    else:
        ce.package_length_mm = round(best.length_mm * 1.12, 1)

    if current_package_w:
        ce.package_width_mm = current_package_w
    else:
        ce.package_width_mm = round(best.width_mm * 1.12, 1)

    if current_package_h:
        ce.package_height_mm = current_package_h
    else:
        ce.package_height_mm = round(best.height_mm * 1.12, 1)

    # Carton — 20% fewer units per carton (poor arrangement)
    naive_units = max(1, int(carton.units_per_carton * 0.75))
    ce.units_per_carton = current_units_per_carton or naive_units
    ce.carton_length_mm = current_carton_l or round(carton.inner_length_mm * 1.10, 1)
    ce.carton_width_mm = current_carton_w or round(carton.inner_width_mm * 1.10, 1)
    ce.carton_height_mm = current_carton_h or round(carton.inner_height_mm * 1.10, 1)

    # Pallet — 20% fewer cartons
    ce.cartons_per_pallet = current_cartons_per_pallet or max(1, int(pallet.cartons_per_pallet * 0.80))

    # Container — worse utilization → more containers needed
    naive_util = best_container.utilization_pct * 0.80
    # Recalculate containers needed with naive utilization
    pkg_vol_litres = (ce.package_length_mm * ce.package_width_mm * ce.package_height_mm) / 1_000_000
    carton_vol = ce.carton_length_mm * ce.carton_width_mm * ce.carton_height_mm / 1e9  # m³
    total_carton_vol = (shipment_quantity / ce.units_per_carton) * carton_vol
    container_vol = best_container.container_volume_m3
    ce.containers_needed = current_containers or max(1, int(total_carton_vol / (container_vol * (naive_util / 100))))

    # Costs
    mat_cost = MATERIALS.get(packaging_material, {}).get("cost_per_sqm", 12.0)
    # Current material usage per package: larger surface area
    ce_pkg_sa = 2 * (
        ce.package_length_mm * ce.package_width_mm
        + ce.package_width_mm * ce.package_height_mm
        + ce.package_height_mm * ce.package_length_mm
    ) / 1_000_000  # m²
    ce.packaging_cost = current_packaging_cost or (shipment_quantity * ce_pkg_sa * mat_cost)
    ce.freight_cost = current_freight_cost or (ce.containers_needed * best_container.freight_cost_per_container)
    ce.total_cost = ce.packaging_cost + ce.freight_cost

    return ce


def _build_comparison(r: PipelineResult) -> list[ComparisonRow]:
    """Build the comparison table rows from pipeline results."""
    c = r.current
    best = r.best_package
    carton = r.carton
    pallet = r.pallet
    bc = r.best_container

    def _pct(current: float, ai: float) -> float:
        """Improvement %: positive means AI is better."""
        if current == 0:
            return 0.0
        return round(((current - ai) / current) * 100, 1)

    rows = [
        ComparisonRow("Package Volume (cm³)", round(c.package_length_mm * c.package_width_mm * c.package_height_mm / 1000, 1), best.volume_cm3, _pct(c.package_length_mm * c.package_width_mm * c.package_height_mm / 1000, best.volume_cm3), "cm³"),
        ComparisonRow("Units Per Carton", float(c.units_per_carton), float(carton.units_per_carton), _pct(float(c.units_per_carton), float(carton.units_per_carton)), "units"),
        ComparisonRow("Cartons Per Pallet", float(c.cartons_per_pallet), float(pallet.cartons_per_pallet), _pct(float(c.cartons_per_pallet), float(pallet.cartons_per_pallet)), "cartons"),
        ComparisonRow("Containers Required", float(c.containers_needed), float(bc.containers_needed), _pct(float(c.containers_needed), float(bc.containers_needed)), "containers"),
        ComparisonRow("Container Utilization", round(bc.utilization_pct * 0.80, 1), bc.utilization_pct, _pct(bc.utilization_pct * 0.80, bc.utilization_pct), "%"),
        ComparisonRow("Packaging Cost (₹)", c.packaging_cost, r.packaging_cost, _pct(c.packaging_cost, r.packaging_cost), "₹"),
        ComparisonRow("Freight Cost (₹)", c.freight_cost, r.freight_cost, _pct(c.freight_cost, r.freight_cost), "₹"),
        ComparisonRow("Total Cost (₹)", c.total_cost, r.total_cost, _pct(c.total_cost, r.total_cost), "₹"),
    ]
    return rows


def run_package_only(
    tea_density: float,
    package_weight: float,
    package_shape: str = "square",
    packaging_material: str = "paper",
) -> list[PackageResult]:
    """Run only the package optimization stage."""
    return optimize_package(
        tea_density=tea_density,
        package_weight=package_weight,
        shape=package_shape,
        material=packaging_material,
    )


def run_carton_only(
    package_length_mm: float,
    package_width_mm: float,
    package_height_mm: float,
    shipment_quantity: int,
    package_weight_g: float,
) -> CartonResult:
    """Run only the carton optimization stage."""
    return optimize_carton(
        package_length_mm=package_length_mm,
        package_width_mm=package_width_mm,
        package_height_mm=package_height_mm,
        shipment_quantity=shipment_quantity,
        package_weight_kg=package_weight_g / 1000.0,
    )


def run_pallet_only(
    carton_length_mm: float,
    carton_width_mm: float,
    carton_height_mm: float,
    carton_weight_kg: float,
) -> PalletResult:
    """Run only the pallet optimization stage."""
    return optimize_pallet(
        carton_length_mm=carton_length_mm,
        carton_width_mm=carton_width_mm,
        carton_height_mm=carton_height_mm,
        carton_weight_kg=carton_weight_kg,
    )


def run_container_only(
    carton_length_mm: float,
    carton_width_mm: float,
    carton_height_mm: float,
    cartons_per_pallet: int,
    pallet_height_m: float,
    shipment_quantity: int,
    units_per_carton: int = 1,
) -> list[ContainerResult]:
    """Run only the container optimization stage."""
    return optimize_container(
        pallet_height_m=pallet_height_m,
        cartons_per_pallet=cartons_per_pallet,
        units_per_carton=units_per_carton,
        shipment_quantity=shipment_quantity,
        carton_length_mm=carton_length_mm,
        carton_width_mm=carton_width_mm,
        carton_height_mm=carton_height_mm,
    )
