"""
Pydantic v2 schemas (DTOs) for Tea Packaging Optimization Platform.
Request/response validation for all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.optimizers.constants import (
    MAX_PACKAGE_WEIGHT_G,
    MIN_PACKAGE_WEIGHT_G,
    MAX_TEA_DENSITY,
    MIN_TEA_DENSITY,
)


# ── Enums ────────────────────────────────────────────────────────────────────

class ShipmentType(str, Enum):
    total_weight = "total_weight"
    per_container = "per_container"


class PackageShape(str, Enum):
    square = "square"
    round = "round"


class PackagingMaterial(str, Enum):
    paper = "paper"
    plastic = "plastic"
    metal = "metal"


class ContainerType(str, Enum):
    gp20 = "20GP"
    gp40 = "40GP"
    hc40 = "40HC"


class SimulationStatus(str, Enum):
    draft = "draft"
    running = "running"
    completed = "completed"
    failed = "failed"


# ── Simulation Create ─────────────────────────────────────────────────────────

class SimulationCreateRequest(BaseModel):
    """Inputs the user provides to start a new optimization."""
    tea_density: float = Field(
        ..., ge=MIN_TEA_DENSITY, le=MAX_TEA_DENSITY,
        description="Tea density in g/cm³ (0.18–0.48 typical)",
        examples=[0.35],
    )
    package_weight: float = Field(
        ..., ge=MIN_PACKAGE_WEIGHT_G, le=MAX_PACKAGE_WEIGHT_G,
        description="Net tea per pouch in grams (e.g. 250, 500, 1000)",
        examples=[250.0],
    )
    shipment_quantity: int = Field(
        ..., gt=0,
        description="Total number of packages to ship",
        examples=[100000],
    )
    shipment_type: ShipmentType = Field(
        default=ShipmentType.total_weight,
        description="How the shipment quantity is interpreted",
    )
    package_shape: PackageShape = Field(
        default=PackageShape.square,
        description="Pouch shape — square (rectangular prism) or round (cylindrical)",
    )
    packaging_material: PackagingMaterial = Field(
        default=PackagingMaterial.paper,
        description="Primary packaging material",
    )
    target_market: Optional[str] = Field(
        default=None, max_length=100,
        description="Optional target market for regulatory constraints",
    )

    model_config = {"extra": "forbid"}


class SimulationCreateResponse(BaseModel):
    """Stub returned after creating a simulation (it runs async)."""
    id: str
    status: SimulationStatus
    message: str

    model_config = {"from_attributes": True}


# ── Package Optimization ──────────────────────────────────────────────────────

class PackageOptionResponse(BaseModel):
    """A single package dimension recommendation."""
    id: str
    simulation_id: str
    volume_cm3: float = Field(
        validation_alias="volume", description="Pouch internal volume, cm³"
    )
    product_volume_cm3: float = Field(
        default=0.0,
        validation_alias="product_volume",
        description="The tea's own volume (mass / density), cm³ — Module 3's Product Volume",
    )
    length_mm: float = Field(validation_alias="length")
    width_mm: float = Field(validation_alias="width")
    height_mm: float = Field(validation_alias="height")
    shape: str
    material: str
    fill_ratio: float
    # Named for its actual unit. It was `material_usage_sqm` while carrying cm²,
    # so the UI rendered a 527 cm² pouch as "527 m²".
    material_usage_cm2: float = Field(
        validation_alias="material_usage",
        description="Pouch material consumed per unit, cm²",
    )
    cost_estimate: float
    is_best: bool
    rank: int

    model_config = {"from_attributes": True, "populate_by_name": True}


class PackageOptimizeResponse(BaseModel):
    """Result of the package optimization stage."""
    best_package: PackageOptionResponse
    alternatives: list[PackageOptionResponse] = []


class PackageOptimizeRequest(BaseModel):
    """Standalone package optimization request (same fields as simulation input)."""
    tea_density: float = Field(..., ge=MIN_TEA_DENSITY, le=MAX_TEA_DENSITY)
    package_weight: float = Field(
        ..., ge=MIN_PACKAGE_WEIGHT_G, le=MAX_PACKAGE_WEIGHT_G
    )
    package_shape: PackageShape = PackageShape.square
    packaging_material: PackagingMaterial = PackagingMaterial.paper

    model_config = {"extra": "forbid"}


# ── Carton Optimization ───────────────────────────────────────────────────────

class CartonConfigResponse(BaseModel):
    """A carton configuration. `length/width/height` are OUTER (purchasable) dims."""
    id: str
    simulation_id: str
    length_mm: float = Field(validation_alias="length")
    width_mm: float = Field(validation_alias="width")
    height_mm: float = Field(validation_alias="height")
    inner_length_mm: float = Field(default=0.0, validation_alias="inner_length")
    inner_width_mm: float = Field(default=0.0, validation_alias="inner_width")
    inner_height_mm: float = Field(default=0.0, validation_alias="inner_height")
    units_per_carton: int
    arrangement: Optional[str] = None
    carton_weight_kg: float = Field(validation_alias="carton_weight")
    board_grade: str
    board_cost_per_carton: Optional[float] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class CartonOptimizeRequest(BaseModel):
    """Standalone carton optimization request."""
    package_length_mm: float = Field(..., gt=0)
    package_width_mm: float = Field(..., gt=0)
    package_height_mm: float = Field(..., gt=0)
    package_weight_g: float = Field(..., gt=0)
    shipment_quantity: int = Field(..., gt=0)

    model_config = {"extra": "forbid"}


class CartonOptimizeResponse(BaseModel):
    """Carton optimization result."""
    config: CartonConfigResponse


# ── Pallet Optimization ───────────────────────────────────────────────────────

class PalletConfigResponse(BaseModel):
    """A pallet configuration."""
    id: str
    simulation_id: str
    cartons_per_layer: int
    layers: int
    cartons_per_pallet: int
    pallet_height_m: float = Field(validation_alias="pallet_height")
    total_weight_kg: float = Field(validation_alias="total_weight")
    layer_pattern: Optional[str] = None
    footprint_utilization_pct: Optional[float] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class PalletOptimizeRequest(BaseModel):
    """Standalone pallet optimization request."""
    carton_length_mm: float = Field(..., gt=0)
    carton_width_mm: float = Field(..., gt=0)
    carton_height_mm: float = Field(..., gt=0)
    carton_weight_kg: float = Field(..., gt=0)

    model_config = {"extra": "forbid"}


class PalletOptimizeResponse(BaseModel):
    """Pallet optimization result."""
    config: PalletConfigResponse


# ── Container Optimization ────────────────────────────────────────────────────

class ContainerConfigResponse(BaseModel):
    """
    A container loading configuration (Module 6).

    Metrics are grouped by view. `*_per_container` describes one full container;
    the rest describes this order. See models.ContainerConfig for why the two are
    kept apart.
    """
    id: str
    simulation_id: str
    container_type: str
    pallets_per_container: Optional[int] = None
    pallet_stack: Optional[int] = 1

    # Capacity view — one full container
    cartons_per_container: int = Field(description="Cartons in one full container")
    units_per_container: int = Field(
        description="Pouches in one full container — Module 6's 'Total Units'"
    )
    capacity_utilization_pct: float = Field(
        description="Packing density of a FULL container — quality of the scheme"
    )
    empty_space_per_container_m3: float = Field(
        description="Unused volume in one full container — Module 6's 'Empty Space'"
    )

    # Shipment view — this order
    containers_needed: int = 1
    total_units_shipped: int = Field(description="Pouches actually shipped by this order")
    utilization_pct: float = Field(
        description="Share of BOOKED volume holding tea — what the freight bill reflects"
    )
    empty_space_total_m3: float = Field(description="Unused volume across all booked containers")

    payload_kg: Optional[float] = None
    freight_cost: float
    is_best: bool

    model_config = {"from_attributes": True}


class ContainerOptimizeRequest(BaseModel):
    """Standalone container optimization request."""
    carton_length_mm: float = Field(..., gt=0)
    carton_width_mm: float = Field(..., gt=0)
    carton_height_mm: float = Field(..., gt=0)
    cartons_per_pallet: int = Field(..., gt=0)
    pallet_height_m: float = Field(..., gt=0)
    shipment_quantity: int = Field(..., gt=0)
    units_per_carton: int = Field(default=1, gt=0)

    model_config = {"extra": "forbid"}


class ContainerOptimizeResponse(BaseModel):
    """Comparison of all container types."""
    best_container: ContainerConfigResponse
    alternatives: list[ContainerConfigResponse] = []


# ── Compare ───────────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    """User-provided current values for comparison."""
    simulation_id: Optional[str] = None
    ship_quantity: int = Field(..., gt=0)
    tea_density: float = Field(..., ge=MIN_TEA_DENSITY, le=MAX_TEA_DENSITY)
    package_weight: float = Field(
        ..., ge=MIN_PACKAGE_WEIGHT_G, le=MAX_PACKAGE_WEIGHT_G
    )
    current_package_length_mm: Optional[float] = None
    current_package_width_mm: Optional[float] = None
    current_package_height_mm: Optional[float] = None
    current_carton_length_mm: Optional[float] = None
    current_carton_width_mm: Optional[float] = None
    current_carton_height_mm: Optional[float] = None
    current_units_per_carton: Optional[int] = None
    current_cartons_per_pallet: Optional[int] = None
    current_containers: Optional[int] = None
    current_packaging_cost: Optional[float] = None
    current_freight_cost: Optional[float] = None

    model_config = {"extra": "forbid"}


class CompareRow(BaseModel):
    """Single comparison row for the dashboard."""
    parameter_name: str
    current_value: float
    ai_value: float
    improvement_pct: float
    unit: str = ""
    driver: str = Field(
        default="",
        description="Why this line moved — the lever responsible, in plain English",
    )

    model_config = {"from_attributes": True}


class CompareResponse(BaseModel):
    """Current vs AI comparison dashboard data."""
    simulation_id: Optional[str] = None
    rows: list[CompareRow] = []
    packaging_cost_current: float = 0.0
    packaging_cost_ai: float = 0.0
    carton_cost_current: float = 0.0
    carton_cost_ai: float = 0.0
    freight_cost_current: float = 0.0
    freight_cost_ai: float = 0.0
    total_cost_current: float = 0.0
    total_cost_ai: float = 0.0
    total_savings: float = 0.0
    baseline_assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "How the 'current practice' figures were derived. Empty when the user "
            "supplied their own current values."
        ),
    )
    baseline_is_user_supplied: bool = False


# ── Full Simulation Detail ────────────────────────────────────────────────────

class SimulationDetailResponse(BaseModel):
    """Complete simulation result with all optimization stages."""
    id: str
    status: SimulationStatus
    created_at: datetime
    updated_at: datetime
    inputs: Optional[SimulationCreateRequest] = None
    best_package: Optional[PackageOptionResponse] = None
    package_alternatives: list[PackageOptionResponse] = []
    carton: Optional[CartonConfigResponse] = None
    pallet: Optional[PalletConfigResponse] = None
    best_container: Optional[ContainerConfigResponse] = None
    container_alternatives: list[ContainerConfigResponse] = []
    comparison: Optional[CompareResponse] = None

    model_config = {"from_attributes": True}


class SimulationListItem(BaseModel):
    """Lightweight simulation entry for list views."""
    id: str
    status: SimulationStatus
    tea_density: Optional[float] = None
    package_weight: Optional[float] = None
    shipment_quantity: Optional[int] = None
    total_cost: Optional[float] = None
    total_savings: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSimulations(BaseModel):
    """Paginated list of simulations."""
    items: list[SimulationListItem]
    total: int
    page: int
    page_size: int


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    """Aggregated dashboard statistics."""
    total_simulations: int
    total_savings: float
    average_container_utilization: float
    recent_simulations: list[SimulationListItem] = []


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str
    code: str = "internal_error"


# ── AI Analysis ────────────────────────────────────────────────────────────────

class StageValidationResponse(BaseModel):
    stage: str
    status: str  # "valid" | "warning" | "invalid"
    message: str


class AIAnalysisResponse(BaseModel):
    validations: list[StageValidationResponse] = []
    summary: str = ""
    error: Optional[str] = None


# ── AI Chat ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """
    A question for the assistant.

    Note there is no field for the API key or for result context: the key lives on
    the server, and the facts are loaded from `simulation_id` server-side so the
    browser cannot feed the assistant invented numbers.
    """

    message: str = Field(..., min_length=1, max_length=2000)
    simulation_id: Optional[str] = Field(
        default=None, description="Grounds the answer in a stored simulation"
    )
    history: list[ChatMessage] = Field(
        default_factory=list, max_length=20, description="Prior turns, oldest first"
    )

    model_config = {"extra": "forbid"}


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[str] = Field(
        default_factory=list,
        description=(
            "Tools the assistant invoked. Non-empty means the numbers in the reply "
            "were computed by the optimiser rather than written by the model."
        ),
    )


# ── Load plan (3D visualisation) ──────────────────────────────────────────────

class PlacementResponse(BaseModel):
    """One item placed in an area, positioned by its lower-left corner (mm)."""

    x: float
    y: float
    rotated: bool = Field(
        description="True when the item's length runs along the area's width"
    )


class BoxDims(BaseModel):
    length_mm: float
    width_mm: float
    height_mm: float


class LoadPlanResponse(BaseModel):
    """
    The real load plan, as computed by the optimiser.

    Sent as a *recipe*, not 1,400 positions: one pallet layer plus one container
    floor, with repeat counts. The client composes the full load by translation
    only — it never re-derives a packing, because it could not: for a `mixed`
    layer pattern, "12 per layer" does not say where the twelfth carton goes.

    Coordinates are millimetres from the lower-left corner of the relevant area.
    """

    simulation_id: str
    container_type: str
    container: BoxDims
    pallet: BoxDims
    pallet_base_height_mm: float = Field(
        description="Height of the empty pallet deck; cartons start above this"
    )
    carton: BoxDims = Field(description="Outer dimensions — what is actually stacked")

    carton_layer: list[PlacementResponse] = Field(
        description="Cartons in ONE pallet layer, in pallet coordinates"
    )
    layers: int = Field(description="Identical layers stacked per pallet")
    layer_pattern: str

    pallet_floor: list[PlacementResponse] = Field(
        description="Pallets on the container floor, in container coordinates"
    )
    pallet_stack: int = Field(description="Pallets stacked high in the container")

    cartons_per_container: int
    pallets_per_container: int
    capacity_utilization_pct: float


# ── Maximum capacity ──────────────────────────────────────────────────────────

class MaxCapacityPackage(BaseModel):
    length_mm: float
    width_mm: float
    height_mm: float
    volume_cm3: float
    product_volume_cm3: float
    fill_ratio: float
    cost_estimate: float
    shape: str
    material: str


class MaxCapacityCarton(BaseModel):
    outer_length_mm: float
    outer_width_mm: float
    outer_height_mm: float
    units_per_carton: int
    arrangement: str
    carton_weight_kg: float
    board_grade: str


class MaxCapacityPallet(BaseModel):
    cartons_per_layer: int
    layers: int
    cartons_per_pallet: int
    pallet_height_m: float
    total_weight_kg: float
    layer_pattern: str
    footprint_utilization_pct: float


class MaxCapacityOption(BaseModel):
    """
    The most that fits in ONE container of this type, and the packing that does it.

    `max_units_per_container` is only comparable *within* a container type — a
    40HC holds more than a 20GP because it is a bigger box, not because it packs
    better. `capacity_utilization_pct` is the measure that compares fairly across
    types.
    """

    container_type: str
    is_recommended_type: bool = Field(
        description="True when this is the container the cost optimiser chose"
    )

    max_cartons_per_container: int
    max_units_per_container: int = Field(description="Max pouches in one full container")
    max_tea_weight_kg: float = Field(description="Tea in one full container")
    capacity_utilization_pct: float = Field(
        description="Share of the container's volume filled — comparable across types"
    )
    pallets_per_container: int
    pallet_stack: int

    payload_kg: float
    max_payload_kg: float
    limited_by: str = Field(description="'volume' or 'weight' — what caps this load")

    # The configuration that achieves it, at the same detail as the recommendation
    package: MaxCapacityPackage
    carton: MaxCapacityCarton
    pallet: MaxCapacityPallet

    # What this packing would cost for the simulation's actual shipment quantity.
    # Always >= the recommendation's total: the optimiser minimises cost, so any
    # other configuration is by definition no cheaper.
    total_cost_for_shipment: float


class MaxCapacityResponse(BaseModel):
    """Maximum capacity per container type for these inputs."""

    simulation_id: str
    options: list[MaxCapacityOption]

    # Headline: the biggest single-container load available
    absolute_max_container_type: str
    absolute_max_units: int
    absolute_max_cartons: int
    absolute_max_tea_weight_kg: float

    # Honest check against the recommendation, like-for-like (same container type)
    recommended_container_type: str
    recommended_units_per_container: int
    max_units_for_recommended_type: int
    gain_pct: float
    cost_delta: float
    already_maximal: bool = Field(
        description="True when the recommended plan already fits the most possible "
        "in its container type"
    )
    verdict: str = Field(description="Plain-English reading of the numbers above")

    # The 3D load plan for the max-packed container. Embedded because this
    # configuration is recomputed rather than stored — the search that found it
    # just ran, so its placement recipes are already in hand, and a separate
    # endpoint would have to re-run the entire search to rebuild them.
    layout: LoadPlanResponse


# ── Reference data ────────────────────────────────────────────────────────────

class PackageWeightOption(BaseModel):
    grams: float
    label: str
    is_default: bool = False

    model_config = {"from_attributes": True}


class TeaDensityOption(BaseModel):
    tea_type: str
    min_density: float
    max_density: float
    typical_density: float

    model_config = {"from_attributes": True}


class MaterialOption(BaseModel):
    key: str
    name: str
    cost_per_sqm: float
    eco_score: float

    model_config = {"from_attributes": True}


class PackageTypeOption(BaseModel):
    key: str
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ContainerSpecOption(BaseModel):
    container_type: str
    name: str
    volume_m3: float
    max_payload_kg: float

    model_config = {"from_attributes": True}


class ReferenceDataResponse(BaseModel):
    """
    Master data backing the form dropdowns.

    Served from the database so the options are business data an analyst can
    revise, rather than arrays hardcoded into the browser bundle and duplicated
    away from the rates the costing actually uses.
    """

    package_weights: list[PackageWeightOption] = []
    tea_densities: list[TeaDensityOption] = []
    materials: list[MaterialOption] = []
    package_types: list[PackageTypeOption] = []
    containers: list[ContainerSpecOption] = []
    min_package_weight_g: float
    max_package_weight_g: float
    min_tea_density: float
    max_tea_density: float
