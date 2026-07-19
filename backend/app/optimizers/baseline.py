"""
Baseline — what a tea exporter ships today, without optimisation.

Why this module exists
----------------------
The comparison is the product. "AI saves you 30%" is only meaningful if the
number it is measured against is real.

The previous implementation derived "current practice" from the optimised answer
by multiplying it by fixed degradation factors (units × 0.75, utilisation × 0.80,
dimensions × 1.12). That guarantees a positive saving by construction and
measures nothing: the "30% saving" was just the constant 0.80 wearing a hat.

This module instead models conventional practice **independently** and then runs
it through the *same* physics and the *same* cost model as the optimiser. The
saving is whatever falls out of the subtraction — and it is allowed to be small,
or negative, because that is what an honest baseline does.

What "conventional practice" means here
---------------------------------------
A real exporter is not incompetent; they are constrained by catalogues and habit.
Modelling them as stupid would be a strawman and would inflate the savings just
as dishonestly as the old multipliers did. So the baseline is a *competent human*:

  1. Pouch    — chosen from a catalogue of off-the-shelf formats, rounding up to
                the smallest stock size that holds the tea. No custom tooling.
  2. Carton   — chosen from a catalogue of stock RSC boxes, picking the one that
                holds the most pouches within the weight limit. A sensible choice.
  3. Pallet   — single carton orientation, no mixed/pinwheel patterns, stacked to
                the 1.8 m limit. This is what hand-drawn pallet plans look like.
  4. Container— 20GP, floor-loaded, pallets not double-stacked. The conventional
                default for tea.

The optimiser beats this by custom-sizing the pouch and carton, rotating cartons
within a layer, double-stacking pallets, and choosing the container type on cost
rather than habit. Every one of those is a real, explainable lever — which is the
point: each saving traces to a decision, not to a fudge factor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.optimizers.joint import fit_rectangles
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
    MATERIALS,
    HEADSPACE_RATIO,
    FREIGHT_RATE_PER_NM,
    DEFAULT_DISTANCE_NM,
)

# ── Catalogues ────────────────────────────────────────────────────────────────
# Off-the-shelf stand-up pouch formats (L × W × H, mm), smallest first.
# These are deliberately *not* volume-optimal — that is the waste the optimiser
# removes, and modelling it is the whole point of the baseline.
STANDARD_POUCH_SIZES_MM: list[tuple[float, float, float]] = [
    (80.0, 50.0, 120.0),
    (100.0, 60.0, 150.0),
    (120.0, 80.0, 180.0),
    (140.0, 90.0, 200.0),
    (160.0, 110.0, 220.0),
    (180.0, 120.0, 240.0),
    (200.0, 140.0, 280.0),
    (240.0, 160.0, 320.0),
]

# Stock regular-slotted-container (RSC) sizes carried by Indian corrugators.
STANDARD_CARTON_SIZES_MM: list[tuple[float, float, float]] = [
    (300.0, 200.0, 200.0),
    (380.0, 280.0, 250.0),
    (400.0, 300.0, 300.0),
    (450.0, 300.0, 250.0),
    (500.0, 350.0, 300.0),
    (600.0, 400.0, 300.0),
]

BASELINE_CONTAINER = "20GP"       # conventional default for tea exports
BASELINE_MAX_CARTON_KG = 25.0


@dataclass
class BaselineResult:
    """Conventional-practice configuration, costed with the same model as the optimiser."""

    # Package
    package_length_mm: float = 0.0
    package_width_mm: float = 0.0
    package_height_mm: float = 0.0
    package_volume_cm3: float = 0.0
    package_fill_ratio: float = 0.0

    # Carton
    carton_length_mm: float = 0.0
    carton_width_mm: float = 0.0
    carton_height_mm: float = 0.0
    units_per_carton: int = 0
    carton_weight_kg: float = 0.0
    board_grade: str = ""

    # Pallet
    cartons_per_layer: int = 0
    layers: int = 0
    cartons_per_pallet: int = 0
    pallet_height_m: float = 0.0
    pallet_weight_kg: float = 0.0

    # Container
    container_type: str = BASELINE_CONTAINER
    pallets_per_container: int = 0
    cartons_per_container: int = 0
    units_per_container: int = 0
    containers_needed: int = 0
    utilization_pct: float = 0.0
    capacity_utilization_pct: float = 0.0
    empty_space_m3: float = 0.0

    # Cost
    cartons_needed: int = 0
    packaging_cost: float = 0.0
    carton_cost: float = 0.0
    freight_cost: float = 0.0
    total_cost: float = 0.0

    # Provenance — every value above traces to one of these
    assumptions: list[str] = field(default_factory=list)
    is_user_supplied: bool = False


def _surface_area_cm2(l_mm: float, w_mm: float, h_mm: float) -> float:
    """Outer surface area of a rectangular pouch, cm²."""
    l, w, h = l_mm / 10.0, w_mm / 10.0, h_mm / 10.0
    return 2.0 * (l * w + l * h + w * h)


def _board_grade_for(weight_kg: float) -> tuple[str, float, float]:
    """Return (grade, thickness_mm, gsm) for a carton of this gross weight."""
    for spec in BOARD_GRADES:
        if weight_kg <= spec["max_weight_kg"]:
            return spec["grade"], spec["thickness_mm"], spec["gsm"]
    return "9-ply", 9.0, 1200.0


def _pick_catalogue_pouch(required_volume_cm3: float) -> tuple[float, float, float]:
    """
    Smallest stock pouch that holds the required volume.

    This is catalogue rounding — the exporter buys the next size up, and pays for
    the air inside it. Falls back to the largest format if nothing fits.
    """
    for l, w, h in STANDARD_POUCH_SIZES_MM:
        if (l * w * h) / 1000.0 >= required_volume_cm3:
            return l, w, h
    return STANDARD_POUCH_SIZES_MM[-1]


def _uniform_layer_fit(
    carton_l: float, carton_w: float, pallet_l: float = PALLET_L_MM, pallet_w: float = PALLET_W_MM
) -> int:
    """
    Cartons per pallet layer in a single uniform orientation.

    The whole layer may be rotated 90° — a packer obviously turns the box to see
    which way fits more. What is NOT modelled is *mixing* orientations within one
    layer (pinwheel/interlock), which takes real planning and is one of the levers
    the optimiser wins on.
    """
    if carton_l <= 0 or carton_w <= 0:
        return 0
    return max(
        int(pallet_l // carton_l) * int(pallet_w // carton_w),
        int(pallet_l // carton_w) * int(pallet_w // carton_l),
    )


def _pick_catalogue_carton(
    pouch_l: float,
    pouch_w: float,
    pouch_h: float,
    package_weight_kg: float,
    pallet_l: float = PALLET_L_MM,
    pallet_w: float = PALLET_W_MM,
    pallet_deck: float = PALLET_H_MM,
) -> tuple[tuple[float, float, float], int, tuple[int, int, int]]:
    """
    Pick the stock carton a competent exporter would pick: the one that yields the
    most tea per pallet, within the weight cap.

    The obvious-looking criterion — "most pouches per carton" — is wrong, and
    modelling it made the baseline a strawman. It chose a 500×350×300 box for 1 kg
    pouches, which tiles a 1200×1000 pallet at 58%, and the resulting savings
    claim (61%) was inflated by the baseline's own incompetence rather than by the
    optimiser's skill.

    Real exporters do not do this. The standard carton sizes exist *because* they
    are pallet-modular: 600×400 and 400×300 divide a EUR pallet exactly. Anyone
    shipping regularly knows which of their boxes stacks well. So the baseline
    scores on units per pallet — carton fill × layer fit × layers — which is the
    quantity a human actually cares about.

    Pouches still go into the stock box in one fixed orientation: choosing a box
    is a decision made once, per-SKU pouch rotation puzzles are not.
    """
    usable_mm = PALLET_MAX_HEIGHT * 1000 - pallet_deck
    best: Optional[tuple] = None

    for dims in STANDARD_CARTON_SIZES_MM:
        cl, cw, ch = dims
        nx, ny, nz = int(cl // pouch_l), int(cw // pouch_w), int(ch // pouch_h)
        units = nx * ny * nz
        if units < 1:
            continue
        if units * package_weight_kg > BASELINE_MAX_CARTON_KG:
            # Human response: under-fill the stock box to respect the weight cap.
            units = int(BASELINE_MAX_CARTON_KG // package_weight_kg)
            if units < 1:
                continue

        per_layer = _uniform_layer_fit(cl, cw, pallet_l, pallet_w)
        if per_layer < 1:
            continue
        layers = max(int(usable_mm // ch), 1)
        units_per_pallet = units * per_layer * layers

        if best is None or units_per_pallet > best[3]:
            best = (dims, units, (nx, ny, nz), units_per_pallet)

    if best is None:
        # No stock carton fits this pouch — the exporter would order a custom box
        # holding exactly one, which is the worst realistic case.
        dims = (pouch_l + 10, pouch_w + 10, pouch_h + 10)
        return dims, 1, (1, 1, 1)
    return best[0], best[1], best[2]


def compute_baseline(
    tea_density: float,
    package_weight_g: float,
    shipment_quantity: int,
    material: str = "paper",
    distance_nm: float = DEFAULT_DISTANCE_NM,
    # The pallet the exporter ships on — identical to the optimiser's, because a
    # comparison where the two sides ride different pallets measures the pallet,
    # not the optimisation.
    pallet: dict | None = None,
    # User-supplied overrides — if the exporter knows their real numbers, those
    # beat any model of "typical practice".
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
) -> BaselineResult:
    """
    Model the exporter's current configuration and cost it.

    Any `current_*` argument supplied by the user overrides the modelled value and
    is reported as user-supplied. Everything else follows catalogue-and-habit.

    Raises:
        ValueError: on non-positive inputs.
    """
    if tea_density <= 0:
        raise ValueError("tea_density must be positive")
    if package_weight_g <= 0:
        raise ValueError("package_weight_g must be positive")
    if shipment_quantity <= 0:
        raise ValueError("shipment_quantity must be positive")

    pal = pallet or {
        "length_mm": PALLET_L_MM,
        "width_mm": PALLET_W_MM,
        "deck_mm": PALLET_H_MM,
        "max_load_kg": PALLET_MAX_LOAD,
        "tare_kg": PALLET_TARE_KG,
    }
    pal_l, pal_w = pal["length_mm"], pal["width_mm"]
    pal_deck, pal_load, pal_tare = pal["deck_mm"], pal["max_load_kg"], pal["tare_kg"]

    r = BaselineResult()
    package_weight_kg = package_weight_g / 1000.0
    net_volume_cm3 = package_weight_g / tea_density
    required_volume_cm3 = net_volume_cm3 * (1.0 + HEADSPACE_RATIO)

    # ── Pouch ────────────────────────────────────────────────────────────────
    if current_package_l and current_package_w and current_package_h:
        r.package_length_mm = current_package_l
        r.package_width_mm = current_package_w
        r.package_height_mm = current_package_h
        r.is_user_supplied = True
        r.assumptions.append("Pouch dimensions supplied by user.")
    else:
        pl, pw, ph = _pick_catalogue_pouch(required_volume_cm3)
        r.package_length_mm, r.package_width_mm, r.package_height_mm = pl, pw, ph
        r.assumptions.append(
            f"Pouch rounded up to the smallest stock format holding "
            f"{required_volume_cm3:.0f} cm³ (incl. {HEADSPACE_RATIO:.0%} headspace)."
        )

    r.package_volume_cm3 = round(
        r.package_length_mm * r.package_width_mm * r.package_height_mm / 1000.0, 2
    )
    r.package_fill_ratio = round(
        min(net_volume_cm3 / r.package_volume_cm3, 1.0) if r.package_volume_cm3 else 0.0,
        3,
    )

    # ── Carton ───────────────────────────────────────────────────────────────
    (cl, cw, ch), units, _arr = _pick_catalogue_carton(
        r.package_length_mm, r.package_width_mm, r.package_height_mm,
        package_weight_kg, pal_l, pal_w, pal_deck,
    )
    r.carton_length_mm = current_carton_l or cl
    r.carton_width_mm = current_carton_w or cw
    r.carton_height_mm = current_carton_h or ch
    r.units_per_carton = current_units_per_carton or units
    if current_carton_l or current_units_per_carton:
        r.is_user_supplied = True
        r.assumptions.append("Carton values supplied by user.")
    else:
        r.assumptions.append(
            f"Carton is the stock {cl:.0f}×{cw:.0f}×{ch:.0f} mm RSC holding "
            f"{units} pouches in a single fixed orientation — chosen from the "
            f"catalogue for the most tea per pallet, not custom-sized."
        )

    gross_kg = r.units_per_carton * package_weight_kg
    grade, _thickness, gsm = _board_grade_for(gross_kg)
    board_area_m2 = (
        2
        * (
            r.carton_length_mm * r.carton_width_mm
            + r.carton_length_mm * r.carton_height_mm
            + r.carton_width_mm * r.carton_height_mm
        )
        / 1e6
        * BOARD_AREA_FACTOR
    )
    r.carton_weight_kg = round(gross_kg + board_area_m2 * gsm / 1000.0, 3)
    r.board_grade = grade

    # ── Pallet — uniform layers; rotation allowed, mixing not ───────────────
    per_layer = max(_uniform_layer_fit(r.carton_length_mm, r.carton_width_mm, pal_l, pal_w), 1)
    usable_mm = PALLET_MAX_HEIGHT * 1000 - pal_deck
    layers_by_height = max(int(usable_mm // r.carton_height_mm), 1)
    layers_by_weight = (
        max(int(pal_load // (per_layer * r.carton_weight_kg)), 1)
        if r.carton_weight_kg > 0
        else layers_by_height
    )
    # Stack strength — the same physics the optimiser obeys, applied here so the
    # comparison stays fair. The bottom carton bears every layer above it, and
    # the grade's safe load caps how high the stack can go.
    #
    # The competent response matters: an earlier version had the baseline BUY
    # heavier board instead, which is the expensive reaction — it pushed the
    # claimed savings to 54% and made the baseline a strawman again. A real
    # exporter's first move is free: stack one layer fewer. So the crush limit
    # simply becomes a third cap on layers, alongside height and pallet load.
    idx = next(i for i, s in enumerate(BOARD_GRADES) if s["grade"] == grade)
    stack_cap_kg = BOARD_GRADES[idx]["max_stack_load_kg"]
    layers_by_crush = (
        max(int(stack_cap_kg // r.carton_weight_kg) + 1, 1)
        if r.carton_weight_kg > 0
        else layers_by_height
    )
    layers = min(layers_by_height, layers_by_weight, layers_by_crush)
    if layers == layers_by_crush and layers < min(layers_by_height, layers_by_weight):
        r.assumptions.append(
            f"Stack limited to {layers} layers so the bottom {grade} carton bears "
            f"at most {stack_cap_kg:.0f} kg — stacking less is the exporter's "
            f"cheapest response to crush risk, not buying heavier board."
        )

    r.cartons_per_layer = per_layer
    r.layers = layers
    r.cartons_per_pallet = current_cartons_per_pallet or (per_layer * layers)
    if current_cartons_per_pallet:
        r.is_user_supplied = True
    else:
        r.assumptions.append(
            f"Pallet built in uniform layers ({per_layer}/layer × {layers} layers); "
            f"the layer is rotated to whichever way fits more, but orientations are "
            f"not mixed within a layer."
        )
    r.pallet_height_m = round((pal_deck + layers * r.carton_height_mm) / 1000.0, 3)
    r.pallet_weight_kg = round(r.cartons_per_pallet * r.carton_weight_kg, 2)

    # ── Container — 20GP, floor-loaded, no pallet stacking ──────────────────
    #
    # Pallets are fitted with the SAME geometry the optimiser uses. Rotating
    # pallets to fit the floor is how a 20GP takes 9-10 EUR pallets rather than 8;
    # every container loader on earth does it, and it is not an insight the AI
    # gets to claim credit for. Reserving it for the optimiser inflated the saving
    # by a whole pallet per container.
    #
    # The levers the optimiser legitimately keeps: custom pouch, custom carton,
    # mixed orientations *within* a pallet layer, double-stacking, and choosing
    # the container type on cost rather than habit.
    ct = CONTAINERS[BASELINE_CONTAINER]
    r.container_type = BASELINE_CONTAINER
    floor = fit_rectangles(
        pal_l, pal_w, ct["internal_l"] * 1000, ct["internal_w"] * 1000
    )
    r.pallets_per_container = max(floor.count, 1)
    r.assumptions.append(
        f"{BASELINE_CONTAINER} floor-loaded with {r.pallets_per_container} pallets; "
        f"pallets not double-stacked."
    )

    r.cartons_per_container = r.pallets_per_container * r.cartons_per_pallet
    r.units_per_container = r.cartons_per_container * r.units_per_carton

    # Respect the payload limit the same way the optimiser does.
    payload = (
        r.cartons_per_container * r.carton_weight_kg
        + r.pallets_per_container * pal_tare
    )
    if payload > ct["max_payload_kg"] and r.carton_weight_kg > 0:
        max_cartons = int(
            (ct["max_payload_kg"] - r.pallets_per_container * PALLET_TARE_KG)
            // r.carton_weight_kg
        )
        r.cartons_per_container = max(max_cartons, 1)
        r.units_per_container = r.cartons_per_container * r.units_per_carton
        r.assumptions.append("Container load capped by payload limit, not volume.")

    r.cartons_needed = math.ceil(shipment_quantity / max(r.units_per_carton, 1))
    r.containers_needed = current_containers or max(
        math.ceil(shipment_quantity / max(r.units_per_container, 1)), 1
    )
    if current_containers:
        r.is_user_supplied = True

    carton_vol_m3 = (
        r.carton_length_mm * r.carton_width_mm * r.carton_height_mm
    ) / 1e9
    booked_vol = r.containers_needed * ct["volume_m3"]
    shipped_vol = r.cartons_needed * carton_vol_m3
    r.utilization_pct = round(min(shipped_vol / booked_vol * 100, 100.0), 2)
    r.capacity_utilization_pct = round(
        min(r.cartons_per_container * carton_vol_m3 / ct["volume_m3"] * 100, 100.0), 2
    )
    r.empty_space_m3 = round(max(booked_vol - shipped_vol, 0.0), 3)

    # ── Cost — identical model to the optimiser ─────────────────────────────
    mat = MATERIALS.get(material, MATERIALS["paper"])
    pouch_cost = (
        _surface_area_cm2(r.package_length_mm, r.package_width_mm, r.package_height_mm)
        * mat["cost_per_sqm"]
        / 10_000.0
    )
    r.packaging_cost = round(
        current_packaging_cost or (shipment_quantity * pouch_cost), 2
    )
    r.carton_cost = round(
        r.cartons_needed * board_area_m2 * BOARD_COST_PER_SQM.get(grade, 35.0), 2
    )
    r.freight_cost = round(
        current_freight_cost
        or (r.containers_needed * FREIGHT_RATE_PER_NM * distance_nm * ct["freight_factor"]),
        2,
    )
    r.total_cost = round(r.packaging_cost + r.carton_cost + r.freight_cost, 2)

    if current_packaging_cost or current_freight_cost:
        r.is_user_supplied = True

    return r
