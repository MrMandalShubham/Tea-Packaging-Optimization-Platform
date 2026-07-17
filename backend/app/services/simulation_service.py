"""
Simulation service — orchestrates optimisation and builds the comparison.

Flow: Inputs → joint search (package+carton+pallet+container solved together)
             → independent baseline (conventional practice)
             → comparison → cost summary

The two halves are deliberately independent: the optimiser does not know the
baseline exists, and the baseline does not know the optimiser's answer. They meet
only in the subtraction. That is what makes the reported saving mean something —
see `optimizers/baseline.py` for why this matters.

Pure computation layer: no database access, so every function here is directly
testable and reusable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.optimizers.joint import (
    optimize_jointly,
    Configuration,
    Constraints,
    SearchResult,
    JointCarton,
    JointPallet,
    JointContainer,
)
from app.optimizers.baseline import compute_baseline, BaselineResult
from app.optimizers.package import PackageResult
from app.optimizers.constants import DEFAULT_DISTANCE_NM

# Retained for the standalone /optimize/* stage endpoints.
from app.optimizers.package import optimize_package
from app.optimizers.carton import optimize_carton, CartonResult
from app.optimizers.pallet import optimize_pallet, PalletResult
from app.optimizers.container import optimize_container, ContainerResult

logger = logging.getLogger(__name__)


@dataclass
class CurrentEstimate:
    """
    The baseline, flattened to the shape the API and DB expect.

    This is a view over `BaselineResult`; the authoritative values and their
    provenance live there.
    """

    package_length_mm: float = 0
    package_width_mm: float = 0
    package_height_mm: float = 0
    carton_length_mm: float = 0
    carton_width_mm: float = 0
    carton_height_mm: float = 0
    units_per_carton: int = 0
    cartons_per_pallet: int = 0
    containers_needed: int = 0
    container_type: str = ""
    utilization_pct: float = 0.0
    packaging_cost: float = 0
    carton_cost: float = 0
    freight_cost: float = 0
    total_cost: float = 0
    assumptions: list[str] = field(default_factory=list)
    is_user_supplied: bool = False


@dataclass
class ComparisonRow:
    parameter_name: str
    current_value: float
    ai_value: float
    improvement_pct: float
    unit: str = ""
    # Plain-English reason this line moved. The assessment asks for optimisation
    # logic that is "transparent and explainable"; an unexplained percentage is
    # neither.
    driver: str = ""


@dataclass
class PipelineResult:
    # Optimised solution
    best_package: Optional[PackageResult] = None
    package_alternatives: list[PackageResult] = field(default_factory=list)
    carton: Optional[JointCarton] = None
    pallet: Optional[JointPallet] = None
    best_container: Optional[JointContainer] = None
    container_alternatives: list[JointContainer] = field(default_factory=list)

    # Full configurations, cheapest per container type (Module 6)
    configurations_by_container: dict[str, Configuration] = field(default_factory=dict)
    alternative_configurations: list[Configuration] = field(default_factory=list)

    # Densest packing — "how many fit in ONE container?", which is a different
    # question from "what is cheapest". See SearchResult.max_capacity.
    max_capacity: Optional[Configuration] = None
    max_capacity_by_container: dict[str, Configuration] = field(default_factory=dict)

    # Baseline
    current: Optional[CurrentEstimate] = None
    baseline: Optional[BaselineResult] = None

    comparison: list[ComparisonRow] = field(default_factory=list)

    # Cost summary (optimised side)
    cartons_needed: int = 0
    packaging_cost: float = 0.0
    carton_cost: float = 0.0
    freight_cost: float = 0.0
    total_cost: float = 0.0
    total_savings: float = 0.0

    # Transparency
    configurations_evaluated: int = 0

    # Echo of the inputs
    tea_density: float = 0.0
    package_weight: float = 0.0
    shipment_quantity: int = 0
    shipment_type: str = ""
    package_shape: str = ""
    packaging_material: str = ""
    target_market: Optional[str] = None


def resolve_shipment_type(
    shipment_quantity: int,
    shipment_type: str,
) -> tuple[int, Optional[int]]:
    """
    Interpret Shipment Quantity according to Shipment Type.

    The brief specifies the field but not its semantics, so this is a documented
    assumption (see docs/assumptions.md). The previous implementation stored the
    field and ignored it — both settings produced byte-identical output.

      total_weight  — the quantity is the whole order. The optimiser uses as many
                      containers as it needs.
      per_container — the quantity must fit in a single container. This answers
                      "can I get this many pouches into one box, and how?", and
                      the optimiser rejects any solution needing a second.

    Returns:
        (pouch_count, max_containers) — max_containers is None when unbounded.

    Raises:
        ValueError: on a non-positive quantity or unknown shipment type.
    """
    if shipment_quantity <= 0:
        raise ValueError("shipment_quantity must be positive")

    if shipment_type == "per_container":
        return int(shipment_quantity), 1
    if shipment_type == "total_weight":
        return int(shipment_quantity), None
    raise ValueError(
        f"Unknown shipment_type {shipment_type!r}; "
        f"expected 'total_weight' or 'per_container'"
    )


def run_full_pipeline(
    tea_density: float,
    package_weight: float,
    shipment_quantity: int,
    shipment_type: str = "total_weight",
    package_shape: str = "square",
    packaging_material: str = "paper",
    target_market: Optional[str] = None,
    constraints: Optional[Constraints] = None,
    distance_nm: float = DEFAULT_DISTANCE_NM,
    # User-supplied "what we do today" values. When absent, the baseline is
    # modelled from catalogue-and-habit instead.
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
    Optimise a shipment and compare it against current practice.

    Args:
        tea_density: g/cm³.
        package_weight: net tea per pouch, grams.
        shipment_quantity: interpreted according to `shipment_type`.
        shipment_type: "total_weight" | "per_container".
        package_shape: "square" | "round".
        packaging_material: "paper" | "plastic" | "metal".
        target_market: optional; recorded, not yet a constraint.
        constraints: physical limits; defaults to industry norms.
        distance_nm: voyage distance for the freight model.
        current_*: the exporter's real figures, if known.

    Returns:
        PipelineResult with the optimised solution, the baseline, and the
        comparison between them.

    Raises:
        ValueError: on invalid inputs or if no configuration is feasible.
    """
    qty, max_containers = resolve_shipment_type(shipment_quantity, shipment_type)

    result = PipelineResult(
        tea_density=tea_density,
        package_weight=package_weight,
        shipment_quantity=qty,
        shipment_type=shipment_type,
        package_shape=package_shape,
        packaging_material=packaging_material,
        target_market=target_market,
    )

    # ── Optimised side: all four stages solved as one problem ────────────────
    search: SearchResult = optimize_jointly(
        tea_density=tea_density,
        package_weight_g=package_weight,
        shipment_quantity=qty,
        shape=package_shape,
        material=packaging_material,
        constraints=constraints,
        distance_nm=distance_nm,
        max_containers=max_containers,
    )
    winner = search.best

    result.best_package, result.package_alternatives = _rank_packages(search)
    result.carton = winner.carton
    result.pallet = winner.pallet
    result.best_container = winner.container
    result.container_alternatives = [
        cfg.container
        for key, cfg in search.by_container_type.items()
        if key != winner.container.container_type
    ]
    result.configurations_by_container = search.by_container_type
    result.alternative_configurations = search.alternatives
    result.max_capacity = search.max_capacity
    result.max_capacity_by_container = search.max_by_container_type
    result.configurations_evaluated = search.evaluated

    result.cartons_needed = winner.cartons_needed
    result.packaging_cost = winner.packaging_cost
    result.carton_cost = winner.carton_cost
    result.freight_cost = winner.freight_cost
    result.total_cost = winner.total_cost

    # ── Baseline side: modelled independently, costed identically ───────────
    baseline = compute_baseline(
        tea_density=tea_density,
        package_weight_g=package_weight,
        shipment_quantity=qty,
        material=packaging_material,
        distance_nm=distance_nm,
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
    result.baseline = baseline
    result.current = _flatten_baseline(baseline)
    result.total_savings = round(baseline.total_cost - result.total_cost, 2)

    if result.total_savings < 0:
        # Honest baselines can lose. Surface it rather than hiding it: it usually
        # means the order is too small to fill a container, so the fixed freight
        # cost dominates and no packaging change can pay for it.
        logger.info(
            "Optimised cost exceeds baseline by %.2f for qty=%d — likely a "
            "sub-container order where freight is fixed.",
            -result.total_savings,
            qty,
        )

    result.comparison = _build_comparison(result)
    return result


def _rank_packages(
    search: SearchResult,
) -> tuple[PackageResult, list[PackageResult]]:
    """
    Re-rank pouches by what the *joint* search chose, not by the package stage.

    `optimize_package` ranks candidates on pouch material efficiency alone, and by
    that measure a cube always wins — it has the least surface area per unit
    volume. But the cube tiles the carton and pallet badly, so the joint search
    routinely picks a different pouch.

    Carrying the package stage's `is_best`/`rank` through would therefore label a
    pouch "Best" that no part of the recommended solution actually uses: the UI
    showed a 93.7 mm cube as Best while the carton was built from a 93 × 79 × 112
    pouch listed under "Alternatives".

    Ranking here is by end-to-end cost, which is the only ranking that means
    anything to the reader. Duplicates are dropped — several configurations often
    share a pouch, and listing it three times is noise.
    """
    from dataclasses import replace

    ordered: list[PackageResult] = []
    seen: set[tuple[float, float, float]] = set()

    for cfg in [search.best, *search.alternatives]:
        p = cfg.package
        key = (p.length_mm, p.width_mm, p.height_mm)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)

    ranked = [
        replace(p, rank=i, is_best=(i == 1)) for i, p in enumerate(ordered, start=1)
    ]
    return ranked[0], ranked[1:]


def _flatten_baseline(b: BaselineResult) -> CurrentEstimate:
    """Project a BaselineResult onto the flat shape the API/DB layer expects."""
    return CurrentEstimate(
        package_length_mm=b.package_length_mm,
        package_width_mm=b.package_width_mm,
        package_height_mm=b.package_height_mm,
        carton_length_mm=b.carton_length_mm,
        carton_width_mm=b.carton_width_mm,
        carton_height_mm=b.carton_height_mm,
        units_per_carton=b.units_per_carton,
        cartons_per_pallet=b.cartons_per_pallet,
        containers_needed=b.containers_needed,
        container_type=b.container_type,
        utilization_pct=b.utilization_pct,
        packaging_cost=b.packaging_cost,
        carton_cost=b.carton_cost,
        freight_cost=b.freight_cost,
        total_cost=b.total_cost,
        assumptions=list(b.assumptions),
        is_user_supplied=b.is_user_supplied,
    )


def _pct_improvement(current: float, ai: float) -> float:
    """Percent reduction from `current` to `ai`. Positive means the AI is better."""
    if current == 0:
        return 0.0
    return round(((current - ai) / current) * 100, 1)


def _pct_increase(current: float, ai: float) -> float:
    """Percent gain from `current` to `ai`. For metrics where higher is better."""
    if current == 0:
        return 0.0
    return round(((ai - current) / current) * 100, 1)


def _build_comparison(r: PipelineResult) -> list[ComparisonRow]:
    """
    Build the Current-vs-AI table (Module 7).

    Every row compares two independently computed numbers, and carries the reason
    it moved so the user can audit the claim rather than trust it.
    """
    c = r.current
    pkg = r.best_package
    carton = r.carton
    pallet = r.pallet
    bc = r.best_container
    b = r.baseline

    current_pkg_vol = (
        c.package_length_mm * c.package_width_mm * c.package_height_mm / 1000.0
    )
    current_carton_vol = (
        c.carton_length_mm * c.carton_width_mm * c.carton_height_mm / 1000.0
    )
    ai_carton_vol = (
        carton.outer_length_mm * carton.outer_width_mm * carton.outer_height_mm / 1000.0
    )

    return [
        ComparisonRow(
            "Package Volume (cm³)",
            round(current_pkg_vol, 1),
            round(pkg.volume_cm3, 1),
            _pct_improvement(current_pkg_vol, pkg.volume_cm3),
            "cm³",
            "Custom-sized pouch instead of rounding up to a stock format.",
        ),
        ComparisonRow(
            "Carton Volume (cm³)",
            round(current_carton_vol, 1),
            round(ai_carton_vol, 1),
            _pct_improvement(current_carton_vol, ai_carton_vol),
            "cm³",
            "Carton sized to tile the pallet rather than taken from the stock range.",
        ),
        ComparisonRow(
            "Units Per Carton",
            float(c.units_per_carton),
            float(carton.units_per_carton),
            _pct_increase(float(c.units_per_carton), float(carton.units_per_carton)),
            "units",
            "Fewer units per carton is often better: a smaller carton tiles the "
            "pallet more densely and stacks two-high in the container.",
        ),
        ComparisonRow(
            "Cartons Per Pallet",
            float(c.cartons_per_pallet),
            float(pallet.cartons_per_pallet),
            _pct_increase(
                float(c.cartons_per_pallet), float(pallet.cartons_per_pallet)
            ),
            "cartons",
            f"Pallet footprint {pallet.footprint_utilization_pct}% via "
            f"{pallet.layer_pattern} layers vs a single fixed orientation.",
        ),
        ComparisonRow(
            "Containers Required",
            float(c.containers_needed),
            float(bc.containers_needed),
            _pct_improvement(float(c.containers_needed), float(bc.containers_needed)),
            "containers",
            f"{bc.container_type} chosen on cost"
            + (
                f" and pallets double-stacked, vs {c.container_type} floor-loaded."
                if bc.pallet_stack > 1
                else f", vs {c.container_type} by convention."
            ),
        ),
        ComparisonRow(
            "Container Utilization",
            c.utilization_pct,
            bc.utilization_pct,
            _pct_increase(c.utilization_pct, bc.utilization_pct),
            "%",
            "Share of the volume you pay freight on that actually holds tea.",
        ),
        ComparisonRow(
            "Packaging Cost (₹)",
            c.packaging_cost,
            r.packaging_cost,
            _pct_improvement(c.packaging_cost, r.packaging_cost),
            "₹",
            "Less pouch material per unit, over the same shipment quantity.",
        ),
        ComparisonRow(
            "Carton Cost (₹)",
            c.carton_cost,
            r.carton_cost,
            _pct_improvement(c.carton_cost, r.carton_cost),
            "₹",
            # This line legitimately goes UP when the optimiser trades a smaller
            # carton (more boxes, more board) for a denser pallet and less freight.
            # Explaining that as "lighter cartons are cheaper" would contradict the
            # number sitting next to it.
            (
                f"Lighter cartons drop the board grade to {carton.board_grade}."
                if r.carton_cost <= c.carton_cost
                else (
                    f"Deliberately higher: {r.cartons_needed:,} smaller cartons cost "
                    f"more board than {b.cartons_needed:,} large ones, but they tile "
                    f"the pallet and stack, which more than pays for itself in freight."
                )
            ),
        ),
        ComparisonRow(
            "Freight Cost (₹)",
            c.freight_cost,
            r.freight_cost,
            _pct_improvement(c.freight_cost, r.freight_cost),
            "₹",
            "Fewer containers on the same voyage.",
        ),
        ComparisonRow(
            "Total Cost (₹)",
            c.total_cost,
            r.total_cost,
            _pct_improvement(c.total_cost, r.total_cost),
            "₹",
            "Packaging + carton board + freight.",
        ),
    ]


# ── Standalone stage runners (POST /optimize/*) ───────────────────────────────
# These expose each stage on its own, per the assessment's endpoint list. They
# are intentionally *not* the pipeline: a stage in isolation cannot see the
# downstream cost, which is exactly the limitation `optimize_jointly` removes.


def run_package_only(
    tea_density: float,
    package_weight: float,
    package_shape: str = "square",
    packaging_material: str = "paper",
) -> list[PackageResult]:
    """Run only the package optimisation stage."""
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
    """Run only the carton optimisation stage."""
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
    """Run only the pallet optimisation stage."""
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
    """Run only the container optimisation stage."""
    return optimize_container(
        pallet_height_m=pallet_height_m,
        cartons_per_pallet=cartons_per_pallet,
        units_per_carton=units_per_carton,
        shipment_quantity=shipment_quantity,
        carton_length_mm=carton_length_mm,
        carton_width_mm=carton_width_mm,
        carton_height_mm=carton_height_mm,
    )
