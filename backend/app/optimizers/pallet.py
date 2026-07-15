"""
Pallet Optimizer — Stage 3 of the optimization pipeline.

Given carton dimensions and weight, calculates the optimal pallet layout:
  - cartons per layer (try both orientations)
  - layers (constrained by height + weight)
  - cartons per pallet
  - pallet height
  - total weight
"""

import math
from dataclasses import dataclass, field

from app.optimizers.constants import (
    PALLET_H,
    PALLET_L_MM,
    PALLET_W_MM,
    PALLET_H_MM,
    PALLET_MAX_LOAD,
    PALLET_MAX_STACK_MM as MAX_STACK_MM,
)


@dataclass
class PalletResult:
    """Output of pallet optimization."""

    cartons_per_layer: int = 0
    layers: int = 0
    cartons_per_pallet: int = 0
    pallet_height_m: float = 0.0
    total_weight_kg: float = 0.0

    # Detailed layout
    cartons_lengthwise: int = 0  # cartons along pallet length
    cartons_widthwise: int = 0  # cartons along pallet width
    orientation: str = ""  # "lengthwise" or "widthwise"


def optimize_pallet(
    carton_length_mm: float,
    carton_width_mm: float,
    carton_height_mm: float,
    carton_weight_kg: float,
) -> PalletResult:
    """
    Calculate optimal pallet configuration.

    The pallet is EUR standard: 1200 mm × 1000 mm.
    We try fitting cartons in both orientations and pick the best.

    Args:
        carton_length_mm: Carton length in mm.
        carton_width_mm:  Carton width in mm.
        carton_height_mm: Carton height in mm.
        carton_weight_kg: Weight of one carton in kg.

    Returns:
        PalletResult with optimal layout.
    """
    candidates: list[PalletResult] = []

    # ── Orientation 1: carton length along pallet length ──
    cl = carton_length_mm
    cw = carton_width_mm
    ch = carton_height_mm

    lengthwise_count = int(PALLET_L_MM / cl)
    widthwise_count = int(PALLET_W_MM / cw)
    per_layer_1 = lengthwise_count * widthwise_count

    if per_layer_1 > 0:
        max_layers_1 = int(MAX_STACK_MM / ch)
        # Weight constraint
        weight_limit_layers = int(PALLET_MAX_LOAD / (per_layer_1 * carton_weight_kg)) if carton_weight_kg > 0 else max_layers_1
        layers_1 = min(max_layers_1, weight_limit_layers, 8)  # practical max ~8 layers

        if layers_1 > 0:
            total_wt = per_layer_1 * layers_1 * carton_weight_kg
            pallet_h = PALLET_H + (layers_1 * ch / 1000)
            candidates.append(PalletResult(
                cartons_per_layer=per_layer_1,
                layers=layers_1,
                cartons_per_pallet=per_layer_1 * layers_1,
                pallet_height_m=round(pallet_h, 3),
                total_weight_kg=round(total_wt, 2),
                cartons_lengthwise=lengthwise_count,
                cartons_widthwise=widthwise_count,
                orientation="lengthwise",
            ))

    # ── Orientation 2: carton length along pallet width ──
    lengthwise_count_2 = int(PALLET_L_MM / cw)
    widthwise_count_2 = int(PALLET_W_MM / cl)
    per_layer_2 = lengthwise_count_2 * widthwise_count_2

    # Avoid duplicate if carton is square (L == W) or produces same count
    if per_layer_2 > 0 and per_layer_2 != per_layer_1:
        max_layers_2 = int(MAX_STACK_MM / ch)
        weight_limit_layers_2 = int(PALLET_MAX_LOAD / (per_layer_2 * carton_weight_kg)) if carton_weight_kg > 0 else max_layers_2
        layers_2 = min(max_layers_2, weight_limit_layers_2, 8)

        if layers_2 > 0:
            total_wt = per_layer_2 * layers_2 * carton_weight_kg
            pallet_h = PALLET_H + (layers_2 * ch / 1000)
            candidates.append(PalletResult(
                cartons_per_layer=per_layer_2,
                layers=layers_2,
                cartons_per_pallet=per_layer_2 * layers_2,
                pallet_height_m=round(pallet_h, 3),
                total_weight_kg=round(total_wt, 2),
                cartons_lengthwise=lengthwise_count_2,
                cartons_widthwise=widthwise_count_2,
                orientation="widthwise",
            ))

    if not candidates:
        # Fallback: at least 1 carton per layer
        layers = min(int(MAX_STACK_MM / ch), 8)
        return PalletResult(
            cartons_per_layer=1,
            layers=layers,
            cartons_per_pallet=layers,
            pallet_height_m=round(PALLET_H + (layers * ch / 1000), 3),
            total_weight_kg=round(layers * carton_weight_kg, 2),
            cartons_lengthwise=1,
            cartons_widthwise=1,
            orientation="single",
        )

    return max(candidates, key=lambda c: c.cartons_per_pallet)
