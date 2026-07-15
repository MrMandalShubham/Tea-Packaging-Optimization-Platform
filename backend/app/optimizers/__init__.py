"""
Optimisation engine for tea packaging.

Two ways in:

  optimize_jointly  — the real engine. Solves package + carton + pallet + container
                      as ONE problem, scored on total landed cost. Use this.

  optimize_package / optimize_carton / optimize_pallet / optimize_container
                    — individual stages, exposed because the brief asks for a
                      POST /optimize/{stage} endpoint each. Useful for inspecting
                      one step, but chaining them is what produces the ~37%
                      container utilisation that `joint.py` exists to fix.

  compute_baseline  — models conventional practice independently, so the reported
                      saving is a measurement rather than an assumption.

All of these are pure functions with no database access, which is what keeps them
unit-testable and cheap to reason about.
"""

from app.optimizers.package import optimize_package, PackageResult
from app.optimizers.carton import optimize_carton, CartonResult
from app.optimizers.pallet import optimize_pallet, PalletResult
from app.optimizers.container import optimize_container, ContainerResult
from app.optimizers.joint import (
    optimize_jointly,
    Configuration,
    Constraints,
    SearchResult,
    JointCarton,
    JointPallet,
    JointContainer,
    fit_rectangles,
)
from app.optimizers.baseline import compute_baseline, BaselineResult

__all__ = [
    # Joint search — the engine
    "optimize_jointly",
    "Configuration",
    "Constraints",
    "SearchResult",
    "JointCarton",
    "JointPallet",
    "JointContainer",
    "fit_rectangles",
    # Baseline
    "compute_baseline",
    "BaselineResult",
    # Individual stages
    "optimize_package",
    "PackageResult",
    "optimize_carton",
    "CartonResult",
    "optimize_pallet",
    "PalletResult",
    "optimize_container",
    "ContainerResult",
]
