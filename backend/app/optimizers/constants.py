"""
Industry-standard constants for tea packaging optimization.

All dimensions in meters unless noted. Weight in kg.
Sources: ISO 668 (containers), ISO 6780 (pallets), tea industry norms.
"""

# ── Container interior dimensions (meters) ──────────────────────────
CONTAINERS = {
    "20GP": {
        "name": "20-foot General Purpose",
        "internal_l": 5.898,
        "internal_w": 2.352,
        "internal_h": 2.385,
        "volume_m3": 33.1,
        "max_payload_kg": 28_200,
        "tare_kg": 2_300,
        "freight_factor": 1.00,  # baseline
    },
    "40GP": {
        "name": "40-foot General Purpose",
        "internal_l": 12.032,
        "internal_w": 2.352,
        "internal_h": 2.385,
        "volume_m3": 67.5,
        "max_payload_kg": 28_800,
        "tare_kg": 3_750,
        "freight_factor": 1.65,
    },
    "40HC": {
        "name": "40-foot High Cube",
        "internal_l": 12.032,
        "internal_w": 2.352,
        "internal_h": 2.698,
        "volume_m3": 76.3,
        "max_payload_kg": 28_600,
        "tare_kg": 3_920,
        "freight_factor": 1.80,
    },
}

# ── Pallet standards (EUR/ISO) ───────────────────────────────────
PALLET_L = 1.200   # m
PALLET_W = 1.000   # m
PALLET_H = 0.150   # m (pallet itself)
PALLET_MAX_LOAD = 1_000.0  # kg
PALLET_MAX_HEIGHT = 1.800  # m (including pallet)

# Pallet dimensions in mm (for convenience)
PALLET_L_MM = int(PALLET_L * 1000)   # 1200 mm
PALLET_W_MM = int(PALLET_W * 1000)   # 1000 mm
PALLET_H_MM = int(PALLET_H * 1000)   # 150  mm
PALLET_MAX_STACK_MM = int((PALLET_MAX_HEIGHT - PALLET_H) * 1000)  # 1650 mm usable

# ── Tea density ranges (g/cm³ → kg/m³) ──────────────────────────
TEA_DENSITY = {
    "black_ctc":   {"min": 0.28, "max": 0.42, "typical": 0.35},
    "black_orthodox": {"min": 0.30, "max": 0.48, "typical": 0.38},
    "green":       {"min": 0.25, "max": 0.40, "typical": 0.32},
    "oolong":      {"min": 0.20, "max": 0.35, "typical": 0.28},
    "white":       {"min": 0.18, "max": 0.30, "typical": 0.24},
    "herbal":      {"min": 0.22, "max": 0.38, "typical": 0.30},
}

# ── Board grade lookup ──────────────────────────────────────────
# A grade must satisfy TWO conditions, not one:
#   max_weight_kg      — the carton's own gross weight (handling strength)
#   max_stack_load_kg  — the load the BOTTOM carton of a stack can bear
#                        long-term without crushing.
#
# The second was missing, and it mattered: a 9.3 kg carton is comfortably 3-ply
# by weight, but at the bottom of a 3-layer pallet with another full pallet
# stacked on top it carries ~48 kg — marginal for 3-ply. Choosing board by
# contents weight alone produced load plans that would slowly crush in transit.
#
# max_stack_load_kg values are CONSERVATIVE DEFAULTS: roughly typical fresh box
# compression (BCT) for cartons this size divided by a 4x safety factor for
# transit duration and humidity. Replace with the client's board supplier data
# or lab BCT results before relying on them for a specific board.
BOARD_GRADES = [
    {"max_weight_kg": 10.0,  "grade": "3-ply",  "thickness_mm": 3.0,  "gsm": 350,  "max_stack_load_kg": 35.0},
    {"max_weight_kg": 20.0,  "grade": "5-ply",  "thickness_mm": 5.0,  "gsm": 600,  "max_stack_load_kg": 80.0},
    {"max_weight_kg": 30.0,  "grade": "7-ply",  "thickness_mm": 7.0,  "gsm": 900,  "max_stack_load_kg": 140.0},
    {"max_weight_kg": float("inf"), "grade": "9-ply", "thickness_mm": 9.0, "gsm": 1200, "max_stack_load_kg": 220.0},
]

# ── Operational clearance ───────────────────────────────────────
# Space a forklift needs above the load to actually place it. The pure geometry
# once produced a double-stacked 40GP plan with 17 mm of roof clearance —
# mathematically valid, physically unloadable. Every real load plan keeps
# working room; 50 mm is a common minimum.
OPERATIONAL_CLEARANCE_MM = 50.0

# ── Packaging material properties ───────────────────────────────
MATERIALS = {
    "paper": {
        "name": "Paper / Kraft",
        "cost_per_sqm": 12.0,     # INR
        "thickness_mm": 0.10,
        "density_g_cm3": 0.8,
        "eco_score": 1.0,         # 1=best
    },
    "plastic": {
        "name": "Plastic / LDPE",
        "cost_per_sqm": 18.0,
        "thickness_mm": 0.08,
        "density_g_cm3": 0.92,
        "eco_score": 0.4,
    },
    "metal": {
        "name": "Metal / Foil Laminate",
        "cost_per_sqm": 45.0,
        "thickness_mm": 0.05,
        "density_g_cm3": 2.7,
        "eco_score": 0.3,
    },
}

# ── Package weight catalogue (retail SKUs) ──────────────────────
# The brief specifies Package Weight as a dropdown, so the exporter picks a SKU
# rather than typing a number. These are the standard retail formats for tea.
#
# This is a *UI catalogue*, not an engine constraint: the optimiser handles any
# positive weight, and the standalone /optimize/* endpoints stay open so an
# analyst can model a non-standard format.
PACKAGE_WEIGHTS_G = [
    {"grams": 25.0, "label": "25 g — Sample / sachet"},
    {"grams": 50.0, "label": "50 g — Sample"},
    {"grams": 100.0, "label": "100 g — Retail small"},
    {"grams": 250.0, "label": "250 g — Retail standard"},
    {"grams": 500.0, "label": "500 g — Retail large"},
    {"grams": 1000.0, "label": "1 kg — Bulk retail"},
    {"grams": 2000.0, "label": "2 kg — Food service"},
]

DEFAULT_PACKAGE_WEIGHT_G = 250.0

# Physical upper bound on a single pouch. A hand-packed retail pouch beyond this
# stops being a pouch and becomes a sack, which this model does not cover.
#
# This exists so the limit is stated once. It was previously the literal `500.0`
# repeated across three Pydantic schemas, which silently rejected 1 kg packs —
# one of the most common tea SKUs — even though the engine costs them correctly.
MAX_PACKAGE_WEIGHT_G = 5000.0
MIN_PACKAGE_WEIGHT_G = 1.0

# ── Tea density bounds ──────────────────────────────────────────
# Real tea sits in 0.18–0.48 g/cm³ (see TEA_DENSITY). The accepted range is wider
# because rejecting an unusual-but-real density is worse than modelling one.
MAX_TEA_DENSITY = 5.0
MIN_TEA_DENSITY = 0.01

# ── Headspace / tolerance ───────────────────────────────────────
HEADSPACE_RATIO = 0.15     # 15% extra volume for pouch
FILL_RATIO_TARGET = 0.85   # 85% fill for packages

# ── Package shape defaults ──────────────────────────────────────
# Square: width ≈ depth; Round: cylindrical
# Dimensions are ratio suggestions for a ~1L equivalent
PACKAGE_SHAPES = {
    "square": {"aspect_ratio": 0.8},   # w/d ≈ l * 0.8
    "round":  {"aspect_ratio": 1.0},   # diameter = height
}

# ── Freight model ───────────────────────────────────────────────
FREIGHT_RATE_PER_NM = 2.5     # INR per nautical mile for baseline container
DEFAULT_DISTANCE_NM = 5000.0  # nautical miles

# ── Corrugated board cost by grade (INR per m² of board) ────────
# Indian corrugated market rates; covers board + conversion + printing.
BOARD_COST_PER_SQM = {
    "3-ply": 22.0,
    "5-ply": 35.0,
    "7-ply": 48.0,
    "9-ply": 62.0,
}

# Board consumed per carton = outer surface area × this factor.
# The excess covers flaps, glue tabs and trim waste.
BOARD_AREA_FACTOR = 1.2

# Tare weight of an empty EUR pallet (kg) — counts against container payload.
PALLET_TARE_KG = 25.0
