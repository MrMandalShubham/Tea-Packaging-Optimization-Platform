"""
Container Optimizer — Stage 4 of the optimization pipeline.

Compares 20GP, 40GP, and 40HC containers for pallet loading.
Calculates utilization, empty space, cartons per container, total units, and freight cost.
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional

from app.optimizers.constants import (
    CONTAINERS,
    PALLET_L_MM,
    PALLET_W_MM,
    FREIGHT_RATE_PER_NM,
    DEFAULT_DISTANCE_NM,
)

logger = logging.getLogger(__name__)

# Pallet stacking: typically 1-high for stability
MAX_PALLET_STACK = 1


@dataclass
class ContainerResult:
    """
    Output of container optimization for a single container type.

    Field names follow the same capacity/shipment split as `joint.JointContainer`
    — see that docstring for why. Keeping one vocabulary across both optimisers
    means a reader never has to ask which `total_units` they are looking at.
    """

    container_type: str = ""         # "20GP", "40GP", "40HC"
    container_name: str = ""
    pallets_per_container: int = 0

    # Capacity view — one full container
    cartons_per_container: int = 0
    units_per_container: int = 0
    capacity_utilization_pct: float = 0.0
    empty_space_per_container_m3: float = 0.0

    # Shipment view — this order
    containers_needed: int = 1
    total_units_shipped: int = 0
    utilization_pct: float = 0.0
    empty_space_total_m3: float = 0.0

    freight_cost_per_container: float = 0.0   # freight cost for ONE container
    total_freight_cost: float = 0.0           # freight cost for ALL containers
    is_best: bool = False

    # Detailed layout
    pallets_lengthwise: int = 0
    pallets_widthwise: int = 0

    # Container spec reference
    container_volume_m3: float = 0.0
    container_max_payload_kg: float = 0.0


def _fit_pallets_in_container(
    container_l_mm: float, container_w_mm: float
) -> tuple[int, int, int]:
    """
    Fit EUR pallets (1200×1000 mm) into a container floor.

    Returns (count, pallets_along_length, pallets_along_width).
    Tries both orientations, picks the best.
    """
    # Orientation A: pallet length along container length
    pal_along_l = int(container_l_mm / PALLET_L_MM)
    pal_along_w = int(container_w_mm / PALLET_W_MM)
    count_a = pal_along_l * pal_along_w

    # Orientation B: pallet length along container width
    pal_along_l_b = int(container_l_mm / PALLET_W_MM)
    pal_along_w_b = int(container_w_mm / PALLET_L_MM)
    count_b = pal_along_l_b * pal_along_w_b

    if count_a >= count_b:
        return count_a, pal_along_l, pal_along_w
    else:
        return count_b, pal_along_l_b, pal_along_w_b


def optimize_container(
    pallet_height_m: float,
    cartons_per_pallet: int,
    units_per_carton: int,
    shipment_quantity: int,
    carton_length_mm: float = 0,
    carton_width_mm: float = 0,
    carton_height_mm: float = 0,
    carton_volume_m3: Optional[float] = None,
    distance_nm: float = DEFAULT_DISTANCE_NM,
) -> list[ContainerResult]:
    """
    Evaluate all container types (20GP, 40GP, 40HC) and return sorted results.

    Args:
        pallet_height_m: Height of one loaded pallet in meters.
        cartons_per_pallet: Number of cartons per pallet.
        units_per_carton: Number of units (packages) per carton.
        shipment_quantity: Total number of packages to ship.
        carton_length_mm: Carton length in mm (used to compute volume if not provided).
        carton_width_mm: Carton width in mm.
        carton_height_mm: Carton height in mm.
        carton_volume_m3: Volume of one carton in m³ (optional; computed if omitted).
        distance_nm: Nautical miles for freight cost calculation.

    Returns:
        List of ContainerResult sorted by best first (highest utilization, lowest cost).
        The first result has is_best=True.
    """
    # Calculate carton volume if not provided
    if carton_volume_m3 is None:
        carton_volume_m3 = (
            (carton_length_mm * carton_width_mm * carton_height_mm) / 1e9
        )

    results: list[ContainerResult] = []

    for ct_key in ["20GP", "40GP", "40HC"]:
        ct = CONTAINERS[ct_key]
        ct_l_mm = ct["internal_l"] * 1000
        ct_w_mm = ct["internal_w"] * 1000
        ct_h_mm = ct["internal_h"] * 1000

        # How many pallets fit on the floor?
        pallet_fit, pal_l, pal_w = _fit_pallets_in_container(ct_l_mm, ct_w_mm)

        if pallet_fit == 0:
            continue

        # Can we stack pallets?
        pallet_stackable = int(ct_h_mm / (pallet_height_m * 1000))
        pallet_stack = min(pallet_stackable, MAX_PALLET_STACK)

        pallets_per_container = pallet_fit * pallet_stack
        cartons_per_container = pallets_per_container * cartons_per_pallet
        units_per_container = cartons_per_container * units_per_carton
        container_volume = ct["volume_m3"]

        # ── Capacity view: one full container ──────────────────────────────
        capacity_volume = cartons_per_container * carton_volume_m3
        capacity_utilization_pct = round((capacity_volume / container_volume) * 100, 2)
        empty_per_container = round(max(container_volume - capacity_volume, 0.0), 3)

        # How many containers does this order need?
        containers_needed = (
            math.ceil(shipment_quantity / units_per_container)
            if units_per_container > 0
            else 1
        )

        # ── Shipment view: what this order books ───────────────────────────
        cartons_needed = (
            math.ceil(shipment_quantity / units_per_carton) if units_per_carton > 0 else 0
        )
        booked_volume = containers_needed * container_volume
        shipped_volume = cartons_needed * carton_volume_m3
        utilization_pct = (
            round(min(shipped_volume / booked_volume * 100, 100.0), 2)
            if booked_volume > 0
            else 0.0
        )
        empty_total = round(max(booked_volume - shipped_volume, 0.0), 3)

        # Freight cost per container (one container)
        freight_per_container = round(
            FREIGHT_RATE_PER_NM * distance_nm * ct["freight_factor"],
            2,
        )
        # Total freight cost
        total_freight = round(containers_needed * freight_per_container, 2)

        results.append(ContainerResult(
            container_type=ct_key,
            container_name=ct["name"],
            pallets_per_container=pallets_per_container,
            cartons_per_container=cartons_per_container,
            units_per_container=units_per_container,
            capacity_utilization_pct=capacity_utilization_pct,
            empty_space_per_container_m3=empty_per_container,
            containers_needed=containers_needed,
            total_units_shipped=shipment_quantity,
            utilization_pct=utilization_pct,
            empty_space_total_m3=empty_total,
            freight_cost_per_container=freight_per_container,
            total_freight_cost=total_freight,
            pallets_lengthwise=pal_l,
            pallets_widthwise=pal_w,
            container_volume_m3=container_volume,
            container_max_payload_kg=ct["max_payload_kg"],
        ))

    if not results:
        raise ValueError("No container type can accommodate the pallets")

    # Best packing density first, then cheapest freight.
    results.sort(key=lambda r: (-r.capacity_utilization_pct, r.total_freight_cost))
    results[0].is_best = True

    return results
