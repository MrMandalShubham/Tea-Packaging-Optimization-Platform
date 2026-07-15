"""
Pydantic v2 schemas (DTOs) for Tea Packaging Optimization Platform.
Request/response validation for all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
        ..., gt=0, le=5.0,
        description="Tea density in g/cm³ (0.2–0.8 typical)",
        examples=[0.45],
    )
    package_weight: float = Field(
        ..., gt=0, le=500.0,
        description="Package weight in grams (e.g. 250, 500, 1000)",
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
    volume_cm3: float = Field(validation_alias="volume")
    length_mm: float = Field(validation_alias="length")
    width_mm: float = Field(validation_alias="width")
    height_mm: float = Field(validation_alias="height")
    shape: str
    material: str
    fill_ratio: float
    material_usage_sqm: float = Field(validation_alias="material_usage")
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
    tea_density: float = Field(..., gt=0, le=5.0)
    package_weight: float = Field(..., gt=0, le=500.0)
    package_shape: PackageShape = PackageShape.square
    packaging_material: PackagingMaterial = PackagingMaterial.paper

    model_config = {"extra": "forbid"}


# ── Carton Optimization ───────────────────────────────────────────────────────

class CartonConfigResponse(BaseModel):
    """A carton configuration."""
    id: str
    simulation_id: str
    length_mm: float = Field(validation_alias="length")
    width_mm: float = Field(validation_alias="width")
    height_mm: float = Field(validation_alias="height")
    units_per_carton: int
    carton_weight_kg: float = Field(validation_alias="carton_weight")
    board_grade: str

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
    """A container loading configuration."""
    id: str
    simulation_id: str
    container_type: str
    cartons_per_container: int
    utilization_pct: float
    empty_space_m3: float
    total_units: int
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
    tea_density: float = Field(..., gt=0, le=5.0)
    package_weight: float = Field(..., gt=0, le=500.0)
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

    model_config = {"from_attributes": True}


class CompareResponse(BaseModel):
    """Current vs AI comparison dashboard data."""
    simulation_id: Optional[str] = None
    rows: list[CompareRow] = []
    packaging_cost_current: float = 0.0
    packaging_cost_ai: float = 0.0
    freight_cost_current: float = 0.0
    freight_cost_ai: float = 0.0
    total_cost_current: float = 0.0
    total_cost_ai: float = 0.0
    total_savings: float = 0.0


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
