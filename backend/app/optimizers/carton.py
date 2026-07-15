"""
Carton Optimizer — Stage 2 of the optimization pipeline.

Given package dimensions and shipment quantity, calculates the optimal
master carton dimensions that maximize units per carton while staying
within weight and dimensional constraints.

Design rules:
  - Inner dimensions = package_dims × arrangement + gaps between packages
  - Board thickness added to inner dimensions for outer dimensions
  - Max carton weight ≤ 25 kg (industry standard)
  - Board grade lookup based on carton weight
  - Maximize units_per_carton within constraints
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import math


# ── Board grade by weight ─────────────────────────────────────────────────────
# (grade, thickness_mm, gsm)
BOARD_GRADES: List[Tuple[str, float, float, float]] = [
    # max_kg, grade, thickness_mm, gsm
    (10.0, "3-ply", 3.0, 350),
    (20.0, "5-ply", 5.0, 600),
    (30.0, "7-ply", 7.0, 900),
    (float("inf"), "9-ply", 9.0, 1200),
]

MAX_CARTON_WEIGHT_KG = 25.0  # industry max
PACKAGE_GAP_MM = 2.0          # 2 mm gap between each package inside carton


@dataclass
class CartonResult:
    """Output of the carton optimization stage."""
    inner_length_mm: float
    inner_width_mm: float
    inner_height_mm: float
    outer_length_mm: float
    outer_width_mm: float
    outer_height_mm: float
    arrangement: Tuple[int, int, int]  # (along_length, along_width, along_height)
    units_per_carton: int
    package_weight_g: float
    carton_weight_kg: float
    board_grade: str
    board_thickness_mm: float


@dataclass
class CartonOptimizer:
    """
    Optimize master carton dimensions for given package dimensions.

    Usage:
        optimizer = CartonOptimizer(package_length_mm=150, package_width_mm=100,
                                    package_height_mm=50, package_weight_g=250.0,
                                    shipment_quantity=100000)
        result = optimizer.optimize()
    """

    package_length_mm: float
    package_width_mm: float
    package_height_mm: float
    package_weight_g: float
    shipment_quantity: int

    # Constraints
    max_carton_weight_kg: float = MAX_CARTON_WEIGHT_KG
    package_gap_mm: float = PACKAGE_GAP_MM

    def optimize(self) -> CartonResult:
        """
        Find the optimal carton arrangement.

        Tries different arrangements of packages inside the carton:
          arrangement = (nx, ny, nz) meaning nx along carton length,
          ny along carton width, nz along carton height.

        Strategy:
          1. Generate candidate arrangements up to reasonable limits
          2. Calculate inner carton dimensions for each arrangement
          3. Filter by weight constraint
          4. Score and rank by units_per_carton (primary), volume efficiency (secondary)
        """
        candidates: List[CartonResult] = []

        # Generate arrangements — iterate through possible counts along each axis
        max_nx = min(20, self.shipment_quantity)  # reasonable upper bound
        max_ny = min(20, self.shipment_quantity)
        max_nz = min(20, self.shipment_quantity)

        for nx in range(1, max_nx + 1):
            for ny in range(1, max_ny + 1):
                for nz in range(1, max_nz + 1):
                    units = nx * ny * nz
                    if units > self.shipment_quantity:
                        continue  # overkill for this shipment

                    # Inner dimensions
                    inner_l = (nx * self.package_length_mm +
                               (nx - 1) * self.package_gap_mm)
                    inner_w = (ny * self.package_width_mm +
                               (ny - 1) * self.package_gap_mm)
                    inner_h = (nz * self.package_height_mm +
                               (nz - 1) * self.package_gap_mm)

                    # Calculate carton weight (packages + tare ~5% of package weight)
                    package_weight_kg = self.package_weight_g / 1000.0
                    carton_weight = units * package_weight_kg * 1.05  # 5% tare for carton board

                    if carton_weight > self.max_carton_weight_kg:
                        continue  # exceeds weight limit

                    if carton_weight > 30.0:
                        continue  # too heavy regardless

                    board_grade, thickness = self._get_board_grade(carton_weight)

                    # Outer dimensions (add 2 × board thickness on each side)
                    outer_l = inner_l + 2 * thickness
                    outer_w = inner_w + 2 * thickness
                    outer_h = inner_h + 2 * thickness

                    # Reasonable outer dimension check
                    if outer_l > 800 or outer_w > 600 or outer_h > 600:
                        continue

                    candidates.append(CartonResult(
                        inner_length_mm=round(inner_l, 1),
                        inner_width_mm=round(inner_w, 1),
                        inner_height_mm=round(inner_h, 1),
                        outer_length_mm=round(outer_l, 1),
                        outer_width_mm=round(outer_w, 1),
                        outer_height_mm=round(outer_h, 1),
                        arrangement=(nx, ny, nz),
                        units_per_carton=units,
                        package_weight_g=self.package_weight_g,
                        carton_weight_kg=round(carton_weight, 3),
                        board_grade=board_grade,
                        board_thickness_mm=thickness,
                    ))

        if not candidates:
            # Fallback: smallest possible carton with 1 unit
            board_grade = "3-ply"
            thickness = 3.0
            carton_weight = 1 * (self.package_weight_g / 1000.0) * 1.05
            return CartonResult(
                inner_length_mm=self.package_length_mm,
                inner_width_mm=self.package_width_mm,
                inner_height_mm=self.package_height_mm,
                outer_length_mm=self.package_length_mm + 2 * thickness,
                outer_width_mm=self.package_width_mm + 2 * thickness,
                outer_height_mm=self.package_height_mm + 2 * thickness,
                arrangement=(1, 1, 1),
                units_per_carton=1,
                package_weight_g=self.package_weight_g,
                carton_weight_kg=round(carton_weight, 3),
                board_grade=board_grade,
                board_thickness_mm=thickness,
            )

        # Score: primary = units_per_carton, secondary = lower carton weight
        def score(c: CartonResult) -> Tuple[float, float]:
            # Prefer more units, then lighter weight (better material efficiency)
            return (c.units_per_carton, -c.carton_weight_kg)

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    @staticmethod
    def _get_board_grade(carton_weight_kg: float) -> Tuple[str, float]:
        """Return (grade_name, thickness_mm) for the given carton weight."""
        for max_kg, grade, thickness, _gsm in BOARD_GRADES:
            if carton_weight_kg <= max_kg:
                return grade, thickness
        return "9-ply", 9.0

    def calculate_effective_cost(self, result: CartonResult,
                                  cartons_needed: int) -> float:
        """
        Estimate carton cost based on board grade.
        Rough formula: cost per carton ≈ gsm × surface_area_m2 × 0.15 INR
        (0.15 is a rough conversion from GSM to INR/m² for corrugated board)
        """
        _, _, _gsm = BOARD_GRADES[0]
        for max_kg, grade, thickness, gsm in BOARD_GRADES:
            if result.carton_weight_kg <= max_kg:
                _gsm = gsm
                break

        # Outer surface area in m²
        outer_l_m = result.outer_length_mm / 1000.0
        outer_w_m = result.outer_width_mm / 1000.0
        outer_h_m = result.outer_height_mm / 1000.0

        # Approximate board area needed (box surface area × 1.2 for flaps)
        surface_area_m2 = 2 * (
            outer_l_m * outer_w_m +
            outer_l_m * outer_h_m +
            outer_w_m * outer_h_m
        ) * 1.2

        cost_per_carton = _gsm * surface_area_m2 * 0.15
        return round(cost_per_carton * cartons_needed, 2)


# ── Convenience function ──────────────────────────────────────────────────────

def optimize_carton(
    package_length_mm: float,
    package_width_mm: float,
    package_height_mm: float,
    shipment_quantity: int,
    package_weight_kg: float,
) -> CartonResult:
    """
    Convenience wrapper around CartonOptimizer.optimize().

    Args:
        package_length_mm: Package length in mm.
        package_width_mm: Package width in mm.
        package_height_mm: Package height in mm.
        shipment_quantity: Total packages to ship.
        package_weight_kg: Weight of one package in kg.

    Returns:
        CartonResult with optimal arrangement.
    """
    optimizer = CartonOptimizer(
        package_length_mm=package_length_mm,
        package_width_mm=package_width_mm,
        package_height_mm=package_height_mm,
        package_weight_g=package_weight_kg * 1000.0,
        shipment_quantity=shipment_quantity,
    )
    return optimizer.optimize()
