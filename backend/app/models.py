"""
SQLAlchemy 2.0 ORM models for Tea Packaging Optimization Platform.

Reference / master data (seeded from optimizers.constants at startup):
  - tea_density_refs        — density ranges per tea type
  - packaging_material_refs — cost and properties per material
  - package_type_refs       — supported pouch geometries
  - board_grade_refs        — corrugated grades by weight class
  - container_specs         — ISO 668 container dimensions
  - pallet_specs            — ISO 6780 pallet dimensions

Transactional data:
  - users
  - simulations
  - simulation_inputs
  - package_options
  - carton_configs
  - pallet_configs
  - container_configs
  - comparison_results
  - cost_summary

The reference tables exist because the brief asks for them, and because the
constants they hold (freight rates, material costs, container dimensions) are
business data an analyst should be able to revise without a code deploy. They are
seeded from `optimizers/constants.py`, which remains the source of truth for the
pure-computation layer so the optimisers stay DB-free and unit-testable.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum as SAEnum,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC timestamp. `datetime.utcnow()` is deprecated from Python 3.12."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── REFERENCE / MASTER DATA ───────────────────────────────────────────────────

class TeaDensityRef(Base):
    """Density envelope per tea type — drives input validation and presets."""

    __tablename__ = "tea_density_refs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tea_type = Column(String(50), unique=True, nullable=False, index=True)
    min_density = Column(Float, nullable=False)  # g/cm³
    max_density = Column(Float, nullable=False)
    typical_density = Column(Float, nullable=False)


class PackagingMaterialRef(Base):
    """Cost and physical properties per packaging material."""

    __tablename__ = "packaging_material_refs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    key = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    cost_per_sqm = Column(Float, nullable=False)  # INR
    thickness_mm = Column(Float, nullable=False)
    density_g_cm3 = Column(Float, nullable=False)
    eco_score = Column(Float, nullable=False)  # 1.0 = best


class PackageTypeRef(Base):
    """Supported pouch geometries."""

    __tablename__ = "package_type_refs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    key = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)


class PackageWeightRef(Base):
    """
    Retail SKU weights offered in the Package Weight dropdown.

    Master data rather than a hardcoded array in the frontend: the brief asks for
    a dropdown, and the set of SKUs an exporter sells is business data that should
    be revisable without a redeploy — the same reasoning as the density and
    material tables.
    """

    __tablename__ = "package_weight_refs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    grams = Column(Float, unique=True, nullable=False, index=True)
    label = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)


class BoardGradeRef(Base):
    """Corrugated board grade selected by carton gross weight."""

    __tablename__ = "board_grade_refs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    grade = Column(String(20), unique=True, nullable=False, index=True)
    max_weight_kg = Column(Float, nullable=False)
    thickness_mm = Column(Float, nullable=False)
    gsm = Column(Float, nullable=False)
    cost_per_sqm = Column(Float, nullable=False)  # INR


class ContainerSpec(Base):
    """ISO 668 container interior dimensions and freight factor."""

    __tablename__ = "container_specs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    container_type = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    internal_length_m = Column(Float, nullable=False)
    internal_width_m = Column(Float, nullable=False)
    internal_height_m = Column(Float, nullable=False)
    volume_m3 = Column(Float, nullable=False)
    max_payload_kg = Column(Float, nullable=False)
    tare_kg = Column(Float, nullable=False)
    freight_factor = Column(Float, nullable=False)


class PalletSpec(Base):
    """ISO 6780 pallet dimensions and load limits."""

    __tablename__ = "pallet_specs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    key = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    length_mm = Column(Float, nullable=False)
    width_mm = Column(Float, nullable=False)
    height_mm = Column(Float, nullable=False)
    max_load_kg = Column(Float, nullable=False)
    max_stack_height_mm = Column(Float, nullable=False)
    tare_kg = Column(Float, nullable=False)


# ── USER ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    simulations = relationship("Simulation", back_populates="user", lazy="selectin")


# ── SIMULATION ────────────────────────────────────────────────────────────────

class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(
        SAEnum("draft", "running", "completed", "failed", name="simulation_status"),
        default="draft",
        nullable=False,
    )
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="simulations")
    inputs = relationship("SimulationInput", back_populates="simulation", uselist=False, lazy="selectin")
    package_options = relationship("PackageOption", back_populates="simulation", lazy="selectin")
    carton_config = relationship("CartonConfig", back_populates="simulation", uselist=False, lazy="selectin")
    pallet_config = relationship("PalletConfig", back_populates="simulation", uselist=False, lazy="selectin")
    container_configs = relationship("ContainerConfig", back_populates="simulation", lazy="selectin")
    comparison_results = relationship("ComparisonResult", back_populates="simulation", lazy="selectin")
    cost_summary = relationship("CostSummary", back_populates="simulation", uselist=False, lazy="selectin")


# ── SIMULATION INPUTS ─────────────────────────────────────────────────────────

class SimulationInput(Base):
    __tablename__ = "simulation_inputs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    tea_density = Column(Float, nullable=False)  # g/cm³
    package_weight = Column(Float, nullable=False)  # kg
    shipment_quantity = Column(Integer, nullable=False)  # total units
    shipment_type = Column(
        SAEnum("total_weight", "per_container", name="shipment_type"),
        nullable=False,
    )
    package_shape = Column(
        SAEnum("square", "round", name="package_shape"),
        nullable=False,
    )
    packaging_material = Column(
        SAEnum("paper", "plastic", "metal", name="packaging_material"),
        nullable=False,
    )
    target_market = Column(String(100), nullable=True)

    simulation = relationship("Simulation", back_populates="inputs")


# ── PACKAGE OPTIONS ───────────────────────────────────────────────────────────

class PackageOption(Base):
    __tablename__ = "package_options"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), nullable=False, index=True)

    volume = Column(Float, nullable=False)  # cm³ — the pouch's internal volume
    # The tea's own volume (mass / density) — Module 3's "Product Volume".
    # Stored rather than derived so a saved simulation reports the same number
    # without re-running the physics.
    product_volume = Column(Float, nullable=False, default=0.0)  # cm³
    length = Column(Float, nullable=False)  # mm
    width = Column(Float, nullable=False)  # mm
    height = Column(Float, nullable=False)  # mm
    shape = Column(String(20), nullable=False)  # square / round
    material = Column(String(20), nullable=False)
    fill_ratio = Column(Float, nullable=False)  # 0.0 – 1.0
    material_usage = Column(Float, nullable=False)  # cm² of material
    cost_estimate = Column(Float, nullable=False)  # INR per unit
    is_best = Column(Boolean, default=False)
    rank = Column(Integer, default=1)  # 1 = best

    simulation = relationship("Simulation", back_populates="package_options")


# ── CARTON CONFIG ─────────────────────────────────────────────────────────────

class CartonConfig(Base):
    """
    Master carton specification.

    Both inner and outer dimensions are stored. Inner sizes the packing of pouches;
    outer is what gets bought, palletised and shipped. Keeping only the inner
    dimensions — as an earlier version did — means the pallet and container stages
    stack cartons as though the board had no thickness.
    """

    __tablename__ = "carton_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    length = Column(Float, nullable=False)  # mm — outer, the purchasable spec
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    inner_length = Column(Float, nullable=False)  # mm — the packing cavity
    inner_width = Column(Float, nullable=False)
    inner_height = Column(Float, nullable=False)

    units_per_carton = Column(Integer, nullable=False)
    arrangement = Column(String(20), nullable=True)  # e.g. "3x5x6"
    carton_weight = Column(Float, nullable=False)  # kg, contents + board
    board_grade = Column(String(20), nullable=False)  # "3-ply" … "9-ply"
    board_area_m2 = Column(Float, nullable=True)
    board_cost_per_carton = Column(Float, nullable=True)  # INR

    simulation = relationship("Simulation", back_populates="carton_config")


# ── PALLET CONFIG ─────────────────────────────────────────────────────────────

class PalletConfig(Base):
    __tablename__ = "pallet_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    cartons_per_layer = Column(Integer, nullable=False)
    layers = Column(Integer, nullable=False)
    cartons_per_pallet = Column(Integer, nullable=False)
    pallet_height = Column(Float, nullable=False)  # m (including pallet)
    total_weight = Column(Float, nullable=False)  # kg
    layer_pattern = Column(String(30), nullable=True)  # uniform-* | mixed
    footprint_utilization_pct = Column(Float, nullable=True)

    simulation = relationship("Simulation", back_populates="pallet_config")


# ── CONTAINER CONFIG ──────────────────────────────────────────────────────────

class ContainerConfig(Base):
    __tablename__ = "container_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), nullable=False, index=True)

    container_type = Column(
        SAEnum("20GP", "40GP", "40HC", name="container_type"),
        nullable=False,
    )
    pallets_per_container = Column(Integer, nullable=True)
    pallet_stack = Column(Integer, nullable=True, default=1)  # pallets stacked high

    # ── Capacity view — properties of one FULL container ────────────────────
    # Quality of the packing scheme, independent of order size.
    cartons_per_container = Column(Integer, nullable=False)
    units_per_container = Column(Integer, nullable=False)  # Module 6 "Total Units"
    capacity_utilization_pct = Column(Float, nullable=False)
    empty_space_per_container_m3 = Column(Float, nullable=False)  # Module 6 "Empty Space"

    # ── Shipment view — what this order books and pays for ──────────────────
    # A one-pouch order packs densely (capacity view) but utilises ~0% of the
    # container it books (shipment view). Both are true; they are not the same
    # number, and storing one column for both is what made a 20GP appear to ship
    # more than a 40GP.
    containers_needed = Column(Integer, nullable=False, default=1)
    total_units_shipped = Column(Integer, nullable=False)
    utilization_pct = Column(Float, nullable=False)  # 0.0 – 100.0
    empty_space_total_m3 = Column(Float, nullable=False)

    payload_kg = Column(Float, nullable=True)
    freight_cost = Column(Float, nullable=False)  # INR, all containers
    is_best = Column(Boolean, default=False)

    simulation = relationship("Simulation", back_populates="container_configs")

    __table_args__ = (
        UniqueConstraint("simulation_id", "container_type", name="uq_sim_container"),
    )


# ── COMPARISON RESULTS ────────────────────────────────────────────────────────

class ComparisonResult(Base):
    __tablename__ = "comparison_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), nullable=False, index=True)

    parameter_name = Column(String(100), nullable=False)
    current_value = Column(Float, nullable=False)
    ai_value = Column(Float, nullable=False)
    improvement_pct = Column(Float, nullable=False)  # negative means AI is worse
    unit = Column(String(20), nullable=True)
    # Why this row moved. Persisted so a saved simulation stays auditable without
    # re-running the optimiser.
    driver = Column(Text, nullable=True)

    simulation = relationship("Simulation", back_populates="comparison_results")


# ── COST SUMMARY ──────────────────────────────────────────────────────────────

class CostSummary(Base):
    __tablename__ = "cost_summary"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    # AI-optimised side
    packaging_cost = Column(Float, nullable=False)  # INR total, pouch material
    carton_cost = Column(Float, nullable=False, default=0.0)  # INR total, board
    freight_cost = Column(Float, nullable=False)  # INR total
    total_cost = Column(Float, nullable=False)  # INR

    # Baseline side — stored explicitly rather than back-derived from savings, so
    # the comparison survives a schema read without recomputation.
    baseline_packaging_cost = Column(Float, nullable=False, default=0.0)
    baseline_carton_cost = Column(Float, nullable=False, default=0.0)
    baseline_freight_cost = Column(Float, nullable=False, default=0.0)
    baseline_total_cost = Column(Float, nullable=False, default=0.0)
    # How the baseline was derived, newline-separated. Persisted so a saved
    # simulation can still justify its savings claim without re-running anything.
    baseline_assumptions = Column(Text, nullable=True)
    baseline_is_user_supplied = Column(Boolean, nullable=False, default=False)

    total_savings = Column(Float, nullable=False, default=0.0)  # baseline − AI

    simulation = relationship("Simulation", back_populates="cost_summary")
