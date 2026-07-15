"""
Optimization engine — 5-stage pipeline for tea packaging optimization.

Stages:
  1. PackageOptimizer   — inner pouch dimensions
  2. CartonOptimizer    — master carton dimensions
  3. PalletOptimizer    — pallet layout
  4. ContainerOptimizer — container selection
  5. Comparison         — current vs AI (in simulation_service)
"""

from app.optimizers.package import optimize_package, PackageResult
from app.optimizers.carton import optimize_carton, CartonResult
from app.optimizers.pallet import optimize_pallet, estimate_current_pallet, PalletResult
from app.optimizers.container import optimize_container, ContainerResult

__all__ = [
    "optimize_package",
    "PackageResult",
    "optimize_carton",
    "CartonResult",
    "optimize_pallet",
    "estimate_current_pallet",
    "PalletResult",
    "optimize_container",
    "ContainerResult",
]
