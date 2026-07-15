"""
Joint Optimizer — Stage 1-4 solved together instead of one after another.

Why this module exists
----------------------
Running the stages in sequence (package → carton → pallet → container) is greedy:
each stage commits to a locally optimal choice that silently constrains every
stage after it. The characteristic failure mode:

    carton maximises units → hits the 25 kg cap → carton is ~570 mm tall
      → only 2 layers fit under the 1.8 m pallet limit → pallet is ~1.3 m
        → int(2.385 m container / 1.3 m pallet) = 1 → ~1.1 m of container
          height is bought and shipped empty.

Every step is defensible on its own and the outcome is ~37% utilisation.

This module enumerates *complete* configurations and scores each on total landed
cost for the real shipment quantity. A carton that holds fewer units but tiles
the pallet and stacks two-high into the container wins, because the score can
see all the way down to the freight bill.

The search space is small enough to enumerate exhaustively (~10^5 configurations,
well under a second), so no metaheuristic is needed — the result is the true
optimum of the model, not an approximation.

Search space
------------
    package candidates (top N by material efficiency)
      × carton arrangements (nx, ny, nz)
        × pallet layer patterns (uniform + mixed-orientation)
          × container types (20GP, 40GP, 40HC)
            × pallet stacking (1-high, 2-high)

Objective
---------
    total_cost = packaging_cost + carton_board_cost + freight_cost

Constraints (all in `Constraints`, all overridable)
--------------------------------------------------
    carton weight, carton outer dims, pallet height, pallet load,
    container payload, container internal dims.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.optimizers.constants import (
    CONTAINERS,
    PALLET_L_MM,
    PALLET_W_MM,
    PALLET_H_MM,
    PALLET_MAX_LOAD,
    PALLET_MAX_HEIGHT,
    PALLET_TARE_KG,
    BOARD_GRADES,
    BOARD_COST_PER_SQM,
    BOARD_AREA_FACTOR,
    FREIGHT_RATE_PER_NM,
    DEFAULT_DISTANCE_NM,
)
from app.optimizers.package import optimize_package, PackageResult


# ── Constraints ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Constraints:
    """
    Physical and operational limits on a packaging configuration.

    These are the levers a packaging engineer would actually argue about, so they
    are data rather than magic numbers buried in the search.
    """

    # Carton
    max_carton_weight_kg: float = 25.0   # manual handling limit
    max_carton_length_mm: float = 800.0
    max_carton_width_mm: float = 600.0
    max_carton_height_mm: float = 600.0
    package_gap_mm: float = 2.0          # clearance between pouches inside a carton

    # Pallet
    max_pallet_height_m: float = PALLET_MAX_HEIGHT   # incl. the pallet itself
    max_pallet_load_kg: float = PALLET_MAX_LOAD
    allow_pallet_stacking: bool = True   # may pallets be double-stacked in-container?
    max_pallet_stack: int = 2

    # Search bounds
    max_units_per_axis: int = 12
    top_n_packages: int = 12

    def __post_init__(self) -> None:
        if self.max_carton_weight_kg <= 0:
            raise ValueError("max_carton_weight_kg must be positive")
        if self.max_pallet_height_m * 1000 <= PALLET_H_MM:
            raise ValueError("max_pallet_height_m must exceed the pallet's own height")
        if self.max_units_per_axis < 1:
            raise ValueError("max_units_per_axis must be >= 1")


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class JointCarton:
    inner_length_mm: float
    inner_width_mm: float
    inner_height_mm: float
    outer_length_mm: float
    outer_width_mm: float
    outer_height_mm: float
    arrangement: tuple[int, int, int]
    units_per_carton: int
    carton_weight_kg: float
    board_grade: str
    board_thickness_mm: float
    board_area_m2: float
    board_cost_per_carton: float

    @property
    def outer_volume_m3(self) -> float:
        return (
            self.outer_length_mm * self.outer_width_mm * self.outer_height_mm
        ) / 1e9


@dataclass
class JointPallet:
    cartons_per_layer: int
    layers: int
    cartons_per_pallet: int
    pallet_height_m: float
    total_weight_kg: float
    layer_pattern: str          # "uniform-lengthwise" | "uniform-widthwise" | "mixed"
    footprint_utilization_pct: float


@dataclass
class JointContainer:
    """
    Container loading result for one container type.

    Every metric here belongs to exactly one of two views, and each is named for
    the view it belongs to. Mixing them is not a naming nitpick — it is the defect
    that made a 20GP look like it shipped more than a 40GP (it doesn't; it just
    needs five boxes instead of two) and that reported 64% utilisation on an order
    of a single pouch.

      CAPACITY view — properties of one FULL container. Measures the quality of
        the packing scheme, independent of how much anyone ordered.
          cartons_per_container, units_per_container,
          capacity_utilization_pct, empty_space_per_container_m3

      SHIPMENT view — what this order actually books and pays for.
          containers_needed, total_units_shipped,
          utilization_pct, empty_space_total_m3

    The two utilisations and the two empty-spaces are complements within their own
    view: capacity_utilization_pct + (empty_per_container / container_volume) = 100%,
    and likewise for the shipment view.
    """

    container_type: str
    container_name: str
    pallets_per_container: int
    pallet_stack: int

    # ── Capacity view ────────────────────────────────────────────────────────
    cartons_per_container: int
    units_per_container: int          # Module 6's "Total Units"
    capacity_utilization_pct: float
    empty_space_per_container_m3: float  # Module 6's "Empty Space"

    # ── Shipment view ────────────────────────────────────────────────────────
    containers_needed: int
    total_units_shipped: int
    utilization_pct: float
    empty_space_total_m3: float

    payload_kg: float
    freight_cost_per_container: float
    total_freight_cost: float
    container_volume_m3: float
    max_payload_kg: float


@dataclass
class Configuration:
    """One complete, costed, end-to-end packaging solution."""

    package: PackageResult
    carton: JointCarton
    pallet: JointPallet
    container: JointContainer

    cartons_needed: int = 0
    packaging_cost: float = 0.0
    carton_cost: float = 0.0
    freight_cost: float = 0.0
    total_cost: float = 0.0
    units_shipped: int = 0
    is_best: bool = False

    @property
    def cost_per_unit(self) -> float:
        return self.total_cost / self.units_shipped if self.units_shipped else 0.0


@dataclass
class SearchResult:
    """Everything the joint search found, shaped for the API layer."""

    best: Configuration
    alternatives: list[Configuration] = field(default_factory=list)
    # Cheapest configuration achievable *with each container type*. This is what
    # Module 6 ("compare 20GP / 40GP / 40HC") needs, and keying by type also
    # satisfies the one-row-per-(simulation, container_type) DB constraint.
    by_container_type: dict[str, Configuration] = field(default_factory=dict)
    evaluated: int = 0


# ── Geometry helpers ──────────────────────────────────────────────────────────

def fit_rectangles(
    item_l: float, item_w: float, area_l: float, area_w: float
) -> tuple[int, str]:
    """
    Fit same-size rectangles into a rectangular area, axis-aligned.

    Tries three patterns and returns the best:
      1. uniform, item length along area length
      2. uniform, item length along area width (rotated 90°)
      3. mixed — a main block in one orientation plus a rotated strip in the
         leftover margin. This is the "pinwheel-lite" pattern real pallet
         planners use, and it is often 1-2 items per layer better than uniform.

    Returns (count, pattern_name).
    """
    if item_l <= 0 or item_w <= 0:
        return 0, "none"

    # 1. uniform, unrotated
    a_cols, a_rows = int(area_l // item_l), int(area_w // item_w)
    count_a = a_cols * a_rows

    # 2. uniform, rotated
    b_cols, b_rows = int(area_l // item_w), int(area_w // item_l)
    count_b = b_cols * b_rows

    # 3. mixed: main block unrotated, rotated strip in the length margin
    count_c = 0
    if a_cols > 0:
        margin_l = area_l - a_cols * item_l
        strip = int(margin_l // item_w) * int(area_w // item_l)
        count_c = count_a + strip

    # 4. mixed: main block rotated, unrotated strip in the length margin
    count_d = 0
    if b_cols > 0:
        margin_l = area_l - b_cols * item_w
        strip = int(margin_l // item_l) * int(area_w // item_w)
        count_d = count_b + strip

    best = max(count_a, count_b, count_c, count_d)
    if best == 0:
        return 0, "none"
    if best == count_c and count_c > max(count_a, count_b):
        return best, "mixed"
    if best == count_d and count_d > max(count_a, count_b):
        return best, "mixed"
    return best, "uniform-lengthwise" if count_a >= count_b else "uniform-widthwise"


def _board_grade_for(weight_kg: float) -> tuple[str, float]:
    """Return (grade, thickness_mm) for a carton of the given gross weight."""
    for spec in BOARD_GRADES:
        if weight_kg <= spec["max_weight_kg"]:
            return spec["grade"], spec["thickness_mm"]
    return "9-ply", 9.0


def _build_carton(
    pkg: PackageResult,
    nx: int,
    ny: int,
    nz: int,
    package_weight_kg: float,
    c: Constraints,
) -> Optional[JointCarton]:
    """
    Build a carton holding nx×ny×nz packages, or None if it breaks a constraint.

    Note the ordering: board grade depends on gross weight, and outer dimensions
    depend on board thickness, so weight must be resolved before geometry.
    """
    units = nx * ny * nz
    gross_kg = units * package_weight_kg

    inner_l = nx * pkg.length_mm + (nx - 1) * c.package_gap_mm
    inner_w = ny * pkg.width_mm + (ny - 1) * c.package_gap_mm
    inner_h = nz * pkg.height_mm + (nz - 1) * c.package_gap_mm

    grade, thickness = _board_grade_for(gross_kg)

    outer_l = inner_l + 2 * thickness
    outer_w = inner_w + 2 * thickness
    outer_h = inner_h + 2 * thickness

    # Carton weight = contents + board tare. Board tare is derived from the actual
    # board area rather than a flat 5% guess.
    board_area_m2 = (
        2
        * (
            outer_l * outer_w + outer_l * outer_h + outer_w * outer_h
        )
        / 1e6
        * BOARD_AREA_FACTOR
    )
    grade_gsm = next(
        (s["gsm"] for s in BOARD_GRADES if s["grade"] == grade), 600
    )
    board_tare_kg = board_area_m2 * grade_gsm / 1000.0
    carton_weight = gross_kg + board_tare_kg

    if carton_weight > c.max_carton_weight_kg:
        return None
    if outer_l > c.max_carton_length_mm:
        return None
    if outer_w > c.max_carton_width_mm:
        return None
    if outer_h > c.max_carton_height_mm:
        return None

    board_cost = board_area_m2 * BOARD_COST_PER_SQM.get(grade, 35.0)

    return JointCarton(
        inner_length_mm=round(inner_l, 1),
        inner_width_mm=round(inner_w, 1),
        inner_height_mm=round(inner_h, 1),
        outer_length_mm=round(outer_l, 1),
        outer_width_mm=round(outer_w, 1),
        outer_height_mm=round(outer_h, 1),
        arrangement=(nx, ny, nz),
        units_per_carton=units,
        carton_weight_kg=round(carton_weight, 3),
        board_grade=grade,
        board_thickness_mm=thickness,
        board_area_m2=round(board_area_m2, 4),
        board_cost_per_carton=round(board_cost, 2),
    )


def _build_pallet(
    carton: JointCarton, max_height_mm: float, c: Constraints
) -> Optional[JointPallet]:
    """
    Build the tallest legal pallet of these cartons under `max_height_mm`.

    `max_height_mm` is passed in rather than read from constraints because it
    depends on the container and stacking choice — this is exactly the coupling
    the sequential pipeline could not express.
    """
    per_layer, pattern = fit_rectangles(
        carton.outer_length_mm, carton.outer_width_mm, PALLET_L_MM, PALLET_W_MM
    )
    if per_layer < 1:
        return None

    usable_mm = max_height_mm - PALLET_H_MM
    if usable_mm < carton.outer_height_mm:
        return None

    layers_by_height = int(usable_mm // carton.outer_height_mm)
    layers_by_weight = (
        int(c.max_pallet_load_kg // (per_layer * carton.carton_weight_kg))
        if carton.carton_weight_kg > 0
        else layers_by_height
    )
    layers = min(layers_by_height, layers_by_weight)
    if layers < 1:
        return None

    load_kg = per_layer * layers * carton.carton_weight_kg
    height_m = (PALLET_H_MM + layers * carton.outer_height_mm) / 1000.0

    footprint = (
        per_layer
        * carton.outer_length_mm
        * carton.outer_width_mm
        / (PALLET_L_MM * PALLET_W_MM)
        * 100
    )

    return JointPallet(
        cartons_per_layer=per_layer,
        layers=layers,
        cartons_per_pallet=per_layer * layers,
        pallet_height_m=round(height_m, 3),
        total_weight_kg=round(load_kg, 2),
        layer_pattern=pattern,
        footprint_utilization_pct=round(min(footprint, 100.0), 1),
    )


# ── The search ────────────────────────────────────────────────────────────────

def optimize_jointly(
    tea_density: float,
    package_weight_g: float,
    shipment_quantity: int,
    shape: str = "square",
    material: str = "paper",
    constraints: Optional[Constraints] = None,
    distance_nm: float = DEFAULT_DISTANCE_NM,
    top_n: int = 5,
    max_containers: Optional[int] = None,
) -> SearchResult:
    """
    Search the full configuration space and return the cheapest solutions.

    Args:
        tea_density: g/cm³.
        package_weight_g: net tea per pouch, grams.
        shipment_quantity: total pouches to ship.
        shape: "square" | "round".
        material: "paper" | "plastic" | "metal".
        constraints: physical limits; defaults to industry norms.
        distance_nm: voyage distance for the freight model.
        top_n: how many distinct alternatives to keep alongside the best.
        max_containers: reject solutions needing more than this many containers.
            Used by the "per container" shipment type, where the whole question is
            whether the order fits in one box.

    Returns:
        SearchResult whose `best` is the global cost minimum of the model.

    Raises:
        ValueError: if no configuration satisfies the constraints.
    """
    if tea_density <= 0:
        raise ValueError("tea_density must be positive")
    if package_weight_g <= 0:
        raise ValueError("package_weight_g must be positive")
    if shipment_quantity <= 0:
        raise ValueError("shipment_quantity must be positive")

    c = constraints or Constraints()
    package_weight_kg = package_weight_g / 1000.0

    packages = optimize_package(
        tea_density=tea_density,
        package_weight=package_weight_g,
        shape=shape,
        material=material,
    )[: c.top_n_packages]

    stacks = [1, 2] if c.allow_pallet_stacking else [1]
    stacks = [s for s in stacks if s <= c.max_pallet_stack]

    best: list[Configuration] = []

    for pkg in packages:
        for nx in range(1, c.max_units_per_axis + 1):
            for ny in range(1, c.max_units_per_axis + 1):
                for nz in range(1, c.max_units_per_axis + 1):
                    if nx * ny * nz > shipment_quantity:
                        break  # more units per carton than we are shipping

                    carton = _build_carton(pkg, nx, ny, nz, package_weight_kg, c)
                    if carton is None:
                        # Weight/height grow monotonically with nz, so once this
                        # trips there is no larger nz worth trying.
                        break

                    for ct_key, ct in CONTAINERS.items():
                        ct_h_mm = ct["internal_h"] * 1000
                        ct_l_mm = ct["internal_l"] * 1000
                        ct_w_mm = ct["internal_w"] * 1000

                        for stack in stacks:
                            # The container height, divided by how many pallets
                            # we intend to stack, caps the pallet build height.
                            cap_mm = min(c.max_pallet_height_m * 1000, ct_h_mm / stack)
                            pallet = _build_pallet(carton, cap_mm, c)
                            if pallet is None:
                                continue

                            floor_fit, _ = fit_rectangles(
                                PALLET_L_MM, PALLET_W_MM, ct_l_mm, ct_w_mm
                            )
                            if floor_fit < 1:
                                continue

                            pallets_per_container = floor_fit * stack
                            cartons_per_container = (
                                pallets_per_container * pallet.cartons_per_pallet
                            )
                            units_per_container = (
                                cartons_per_container * carton.units_per_carton
                            )
                            if units_per_container < 1:
                                continue

                            payload = (
                                cartons_per_container * carton.carton_weight_kg
                                + pallets_per_container * PALLET_TARE_KG
                            )
                            if payload > ct["max_payload_kg"]:
                                continue

                            containers_needed = math.ceil(
                                shipment_quantity / units_per_container
                            )
                            if (
                                max_containers is not None
                                and containers_needed > max_containers
                            ):
                                continue
                            cartons_needed = math.ceil(
                                shipment_quantity / carton.units_per_carton
                            )

                            # ── Capacity view: one full container ──────────
                            capacity_vol = cartons_per_container * carton.outer_volume_m3
                            capacity_util = capacity_vol / ct["volume_m3"] * 100
                            empty_per_container = max(
                                ct["volume_m3"] - capacity_vol, 0.0
                            )

                            # ── Shipment view: what this order books ───────
                            # The last container is usually part-empty and the
                            # customer pays freight on that air regardless.
                            booked_vol = containers_needed * ct["volume_m3"]
                            shipped_vol = cartons_needed * carton.outer_volume_m3
                            util = shipped_vol / booked_vol * 100
                            empty_total = max(booked_vol - shipped_vol, 0.0)

                            freight_per = (
                                FREIGHT_RATE_PER_NM * distance_nm * ct["freight_factor"]
                            )
                            freight_total = containers_needed * freight_per
                            packaging_cost = shipment_quantity * pkg.cost_estimate
                            carton_cost = cartons_needed * carton.board_cost_per_carton
                            total = packaging_cost + carton_cost + freight_total

                            container = JointContainer(
                                container_type=ct_key,
                                container_name=ct["name"],
                                pallets_per_container=pallets_per_container,
                                pallet_stack=stack,
                                cartons_per_container=cartons_per_container,
                                units_per_container=units_per_container,
                                capacity_utilization_pct=round(
                                    min(capacity_util, 100.0), 2
                                ),
                                empty_space_per_container_m3=round(
                                    empty_per_container, 3
                                ),
                                containers_needed=containers_needed,
                                total_units_shipped=shipment_quantity,
                                utilization_pct=round(min(util, 100.0), 2),
                                empty_space_total_m3=round(empty_total, 3),
                                payload_kg=round(payload, 1),
                                freight_cost_per_container=round(freight_per, 2),
                                total_freight_cost=round(freight_total, 2),
                                container_volume_m3=ct["volume_m3"],
                                max_payload_kg=ct["max_payload_kg"],
                            )

                            best.append(
                                Configuration(
                                    package=pkg,
                                    carton=carton,
                                    pallet=pallet,
                                    container=container,
                                    cartons_needed=cartons_needed,
                                    packaging_cost=round(packaging_cost, 2),
                                    carton_cost=round(carton_cost, 2),
                                    freight_cost=round(freight_total, 2),
                                    total_cost=round(total, 2),
                                    units_shipped=shipment_quantity,
                                )
                            )

    if not best:
        if max_containers is not None:
            raise ValueError(
                f"{shipment_quantity:,} pouches cannot be loaded into "
                f"{max_containers} container(s) under the current constraints. "
                f"Reduce the quantity, or switch shipment type to 'total_weight' "
                f"to let the optimiser use as many containers as it needs."
            )
        raise ValueError(
            "No packaging configuration satisfies the given constraints. "
            "Try relaxing max_carton_weight_kg or max_pallet_height_m."
        )

    # Cheapest wins. Ties break toward the denser packing scheme, which absorbs
    # order growth without needing a redesign.
    best.sort(key=lambda x: (x.total_cost, -x.container.capacity_utilization_pct))

    # Cheapest option for each container type — Module 6's comparison.
    by_type: dict[str, Configuration] = {}
    for cfg in best:
        by_type.setdefault(cfg.container.container_type, cfg)

    # Keep only one representative per (container, carton size, stacking) shape so
    # the alternatives are genuinely different trade-offs a planner could choose
    # between, rather than five roundings of the same answer. `best` is already
    # cost-sorted, so the first hit for each shape is that shape's cheapest.
    distinct: list[Configuration] = []
    seen: set[tuple] = set()
    for cfg in best:
        key = (
            cfg.container.container_type,
            cfg.container.pallet_stack,
            cfg.carton.units_per_carton,
        )
        if key in seen:
            continue
        seen.add(key)
        distinct.append(cfg)
        if len(distinct) > top_n:
            break

    winner = distinct[0]
    winner.is_best = True

    return SearchResult(
        best=winner,
        alternatives=distinct[1:],
        by_container_type=by_type,
        evaluated=len(best),
    )
