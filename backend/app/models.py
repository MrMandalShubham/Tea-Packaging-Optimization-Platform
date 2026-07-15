"""
SQLAlchemy 2.0 ORM models for Tea Packaging Optimization Platform.

Tables:
  - users
  - simulations
  - simulation_inputs
  - package_options
  - carton_configs
  - pallet_configs
  - container_configs
  - comparison_results
  - cost_summary
"""

import uuid
from datetime import datetime

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
    return datetime.utcnow()


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

    volume = Column(Float, nullable=False)  # cm³
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
    __tablename__ = "carton_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    length = Column(Float, nullable=False)  # mm (inner)
    width = Column(Float, nullable=False)  # mm (inner)
    height = Column(Float, nullable=False)  # mm (inner)
    units_per_carton = Column(Integer, nullable=False)
    carton_weight = Column(Float, nullable=False)  # kg
    board_grade = Column(String(20), nullable=False)  # "3-ply", "5-ply", "7-ply"

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
    cartons_per_container = Column(Integer, nullable=False)
    utilization_pct = Column(Float, nullable=False)  # 0.0 – 100.0
    empty_space_m3 = Column(Float, nullable=False)
    total_units = Column(Integer, nullable=False)
    freight_cost = Column(Float, nullable=False)  # INR
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

    simulation = relationship("Simulation", back_populates="comparison_results")


# ── COST SUMMARY ──────────────────────────────────────────────────────────────

class CostSummary(Base):
    __tablename__ = "cost_summary"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    simulation_id = Column(UUID(as_uuid=False), ForeignKey("simulations.id"), unique=True, nullable=False)

    packaging_cost = Column(Float, nullable=False)  # INR total
    freight_cost = Column(Float, nullable=False)  # INR total
    total_cost = Column(Float, nullable=False)  # INR
    total_savings = Column(Float, nullable=False, default=0.0)  # INR saved vs current

    simulation = relationship("Simulation", back_populates="cost_summary")
