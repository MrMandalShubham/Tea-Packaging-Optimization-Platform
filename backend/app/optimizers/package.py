"""
Package Optimizer — Stage 1 of the optimization pipeline.

Calculates optimal inner pouch dimensions given tea density and weight.
Generates multiple dimension candidates, scores them on material efficiency,
and returns the best plus alternatives.
"""

import math
from dataclasses import dataclass
from typing import Optional

from app.optimizers.constants import (
    HEADSPACE_RATIO,
    FILL_RATIO_TARGET,
    MATERIALS,
    PACKAGE_SHAPES,
)


@dataclass
class PackageResult:
    """
    Result of package dimension optimization.

    Three volumes are in play and they are not interchangeable:

      product_volume_cm3 — the tea itself, mass / density. Module 3's
                           "Product Volume". Fixed by the inputs.
      volume_cm3         — the pouch's internal volume. Larger than the product,
                           because tea needs headspace to settle and seal.
      headspace_cm3      — the difference.

    `product_volume_cm3` is carried rather than recomputed downstream: it was
    previously a local variable inside `optimize_package`, so the API could not
    report it and the UI would have had to redo `weight / density` itself —
    putting a piece of the physics in the browser.
    """

    length_mm: float
    width_mm: float
    height_mm: float
    volume_cm3: float
    product_volume_cm3: float
    surface_area_cm2: float
    fill_ratio: float
    cost_estimate: float
    shape: str = "square"
    material: str = "paper"
    material_usage: float = 0.0
    rank: int = 1
    is_best: bool = False
    score: float = 0.0

    @property
    def headspace_cm3(self) -> float:
        """Air inside the pouch — pouch volume less the tea."""
        return round(max(self.volume_cm3 - self.product_volume_cm3, 0.0), 2)


def _surface_area_square(length_mm: float, width_mm: float, height_mm: float) -> float:
    """Surface area of a rectangular pouch (cm²). All inputs in mm."""
    l, w, h = length_mm / 10.0, width_mm / 10.0, height_mm / 10.0
    return 2.0 * (l * w + l * h + w * h)


def _surface_area_round(diameter_mm: float, height_mm: float) -> float:
    """Surface area of a cylindrical pouch (cm²). All inputs in mm."""
    d, h = diameter_mm / 10.0, height_mm / 10.0
    r = d / 2.0
    return 2.0 * math.pi * r * h + 2.0 * math.pi * r * r  # lateral + two circular ends


def _generate_dimensions_square(volume_cm3: float) -> list[dict]:
    """
    Generate candidate dimensions for a square/rectangular pouch.

    V = L × W × H. We try different aspect ratios where W ≈ L (nearly square base)
    and H varies between 0.3× and 1.0× of the base dimension.
    """
    candidates = []
    # Try H:L ratios: tall, medium, flat
    height_ratios = [1.0, 0.75, 0.6, 0.45, 0.35, 1.2, 1.5]

    for ratio in height_ratios:
        # L ≈ W, H = ratio × L
        # V = L² × ratio × L = ratio × L³
        # L = (V / ratio)^(1/3)
        l_cm = (volume_cm3 / ratio) ** (1.0 / 3.0)
        w_cm = l_cm  # square base approximation
        h_cm = ratio * l_cm

        # Also try slight rectangle variants
        for w_mult in [1.0, 0.85, 0.7]:
            l_cm_adj = (volume_cm3 / (ratio * w_mult)) ** (1.0 / 3.0)
            w_cm_adj = w_mult * l_cm_adj
            h_cm_adj = ratio * l_cm_adj

            l_mm = round(l_cm_adj * 10.0, 1)
            w_mm = round(w_cm_adj * 10.0, 1)
            h_mm = round(h_cm_adj * 10.0, 1)

            actual_volume = (l_mm / 10.0) * (w_mm / 10.0) * (h_mm / 10.0)
            if actual_volume <= 0:
                continue

            candidates.append({
                "length_mm": l_mm,
                "width_mm": w_mm,
                "height_mm": h_mm,
                "volume_cm3": round(actual_volume, 2),
            })

    # Deduplicate by rounded dimensions
    seen = set()
    unique = []
    for c in candidates:
        key = (c["length_mm"], c["width_mm"], c["height_mm"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _generate_dimensions_round(volume_cm3: float) -> list[dict]:
    """
    Generate candidate dimensions for a round/cylindrical pouch.

    V = π × r² × H. We try different D:H ratios.
    """
    candidates = []
    # D:H ratios
    diameter_ratios = [1.0, 0.8, 0.6, 1.2, 1.5, 2.0, 0.5]

    for ratio in diameter_ratios:
        # D = ratio × H, so H = (4V / (π × ratio²))^(1/3)
        h_cm = ((4.0 * volume_cm3) / (math.pi * ratio * ratio)) ** (1.0 / 3.0)
        d_cm = ratio * h_cm

        d_mm = round(d_cm * 10.0, 1)
        h_mm = round(h_cm * 10.0, 1)

        actual_volume = math.pi * (d_mm / 20.0) ** 2 * (h_mm / 10.0)
        if actual_volume <= 0:
            continue

        candidates.append({
            "diameter_mm": d_mm,
            "height_mm": h_mm,
            "volume_cm3": round(actual_volume, 2),
        })

    seen = set()
    unique = []
    for c in candidates:
        key = (c["diameter_mm"], c["height_mm"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _score_candidate_square(
    candidate: dict,
    target_volume_cm3: float,
    material: str,
) -> dict:
    """Score a square package candidate by cost, fill ratio, and practicality."""
    l, w, h = candidate["length_mm"], candidate["width_mm"], candidate["height_mm"]
    actual_vol = candidate["volume_cm3"]

    sa_cm2 = _surface_area_square(l, w, h)
    fill_ratio = target_volume_cm3 / actual_vol if actual_vol > 0 else 0
    fill_ratio = min(fill_ratio, 1.0)

    # Penalty for extreme aspect ratios (too tall or too flat are less practical)
    max_dim = max(l, w, h)
    min_dim = min(l, w, h)
    aspect_penalty = 1.0
    if min_dim > 0:
        aspect_ratio = max_dim / min_dim
        if aspect_ratio > 4.0:
            aspect_penalty = 0.7
        elif aspect_ratio > 3.0:
            aspect_penalty = 0.85
        elif aspect_ratio > 2.5:
            aspect_penalty = 0.95

    mat = MATERIALS.get(material, MATERIALS["paper"])
    cost_per_cm2 = mat["cost_per_sqm"] / 10_000.0  # INR per cm²
    cost_estimate = sa_cm2 * cost_per_cm2  # INR per pouch

    # Score: lower cost = better, but penalized by bad fill ratio and aspect ratio
    # Normalize: fill_ratio closer to FILL_RATIO_TARGET = better
    fill_score = 1.0 - abs(fill_ratio - FILL_RATIO_TARGET)
    score = (1.0 / (cost_estimate + 0.001)) * fill_score * aspect_penalty

    return {
        "length_mm": l,
        "width_mm": w,
        "height_mm": h,
        "volume_cm3": actual_vol,
        "surface_area_cm2": round(sa_cm2, 2),
        "fill_ratio": round(fill_ratio, 3),
        "cost_estimate": round(cost_estimate, 4),
        "score": round(score, 6),
    }


def _score_candidate_round(
    candidate: dict,
    target_volume_cm3: float,
    material: str,
) -> dict:
    """Score a round package candidate."""
    d, h = candidate["diameter_mm"], candidate["height_mm"]
    actual_vol = candidate["volume_cm3"]

    sa_cm2 = _surface_area_round(d, h)
    fill_ratio = target_volume_cm3 / actual_vol if actual_vol > 0 else 0
    fill_ratio = min(fill_ratio, 1.0)

    # Aspect ratio penalty
    aspect_ratio = d / h if h > 0 else 999
    aspect_penalty = 1.0
    if aspect_ratio > 4.0 or aspect_ratio < 0.25:
        aspect_penalty = 0.7
    elif aspect_ratio > 3.0 or aspect_ratio < 0.33:
        aspect_penalty = 0.85

    mat = MATERIALS.get(material, MATERIALS["paper"])
    cost_per_cm2 = mat["cost_per_sqm"] / 10_000.0
    cost_estimate = sa_cm2 * cost_per_cm2

    fill_score = 1.0 - abs(fill_ratio - FILL_RATIO_TARGET)
    score = (1.0 / (cost_estimate + 0.001)) * fill_score * aspect_penalty

    return {
        "diameter_mm": d,
        "height_mm": h,
        "volume_cm3": actual_vol,
        "surface_area_cm2": round(sa_cm2, 2),
        "fill_ratio": round(fill_ratio, 3),
        "cost_estimate": round(cost_estimate, 4),
        "score": round(score, 6),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def optimize_package(
    tea_density: float,        # g/cm³
    package_weight: float,     # grams
    shape: str = "square",     # "square" | "round"
    material: str = "paper",   # "paper" | "plastic" | "metal"
    num_alternatives: int = 2,
) -> list[PackageResult]:
    """
    Calculate optimal package dimensions.

    Args:
        tea_density: Tea density in g/cm³.
        package_weight: Target weight per package in grams.
        shape: 'square' for rectangular, 'round' for cylindrical.
        material: Packaging material key.
        num_alternatives: Number of alternative options to return.

    Returns:
        List of PackageResult, sorted best-first (index 0 = best).
    """
    # Step 1: Calculate net volume needed for the tea
    net_volume_cm3 = package_weight / tea_density  # V = m / ρ

    # Step 2: Add headspace (15%)
    total_volume_cm3 = net_volume_cm3 * (1.0 + HEADSPACE_RATIO)

    # Step 3: Generate dimension candidates
    if shape == "round":
        candidates_raw = _generate_dimensions_round(total_volume_cm3)
        scored = [
            _score_candidate_round(c, net_volume_cm3, material)
            for c in candidates_raw
        ]
        # Normalize to standard format
        for s in scored:
            s["length_mm"] = s["diameter_mm"]
            s["width_mm"] = s["diameter_mm"]
    else:
        candidates_raw = _generate_dimensions_square(total_volume_cm3)
        scored = [
            _score_candidate_square(c, net_volume_cm3, material)
            for c in candidates_raw
        ]

    # Step 4: Sort by score (descending), deduplicate
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Remove duplicates with nearly identical dimensions
    deduped = []
    for s in scored:
        is_dup = False
        for d in deduped:
            if (abs(s["length_mm"] - d["length_mm"]) < 2 and
                abs(s["width_mm"] - d["width_mm"]) < 2 and
                abs(s["height_mm"] - d["height_mm"]) < 2):
                is_dup = True
                break
        if not is_dup:
            deduped.append(s)

    # Step 5: Convert to PackageResult objects
    results = []
    for rank, entry in enumerate(deduped, start=1):
        results.append(PackageResult(
            length_mm=entry["length_mm"],
            width_mm=entry["width_mm"],
            height_mm=entry["height_mm"],
            volume_cm3=entry["volume_cm3"],
            product_volume_cm3=round(net_volume_cm3, 2),
            surface_area_cm2=entry.get("surface_area_cm2", 0.0),
            fill_ratio=entry["fill_ratio"],
            cost_estimate=entry["cost_estimate"],
            shape=shape,
            material=material,
            material_usage=entry.get("surface_area_cm2", 0.0),  # cm²
            rank=rank,
            is_best=(rank == 1),
            score=entry.get("score", 0.0),
        ))

    if not results:
        raise ValueError("Could not generate any valid package dimensions")

    return results
