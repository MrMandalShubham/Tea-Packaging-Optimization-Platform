"""
Pytest fixtures for optimizer tests.
"""
import pytest
import sys
from pathlib import Path

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.optimizers.constants import (
    CONTAINERS,
    MATERIALS,
    BOARD_GRADES,
    TEA_DENSITY,
    HEADSPACE_RATIO,
    FILL_RATIO_TARGET,
    PALLET_L,
    PALLET_W,
    PALLET_MAX_LOAD,
)


@pytest.fixture
def sample_tea_density() -> float:
    return 0.35  # typical black CTC


@pytest.fixture
def sample_package_weight() -> float:
    return 250.0  # 250g pouch


@pytest.fixture
def sample_shipment_qty() -> int:
    return 100_000  # 100k units


@pytest.fixture
def sample_package_dims():
    """Typical package dimensions for 250g black tea."""
    return {"length_mm": 120.0, "width_mm": 95.0, "height_mm": 60.0, "weight_g": 250.0}


@pytest.fixture
def sample_carton_dims():
    """Typical carton config."""
    return {"length_mm": 380.0, "width_mm": 290.0, "height_mm": 250.0, "weight_kg": 18.0}
