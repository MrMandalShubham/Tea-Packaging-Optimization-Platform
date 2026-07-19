"""
Seed the reference tables from `optimizers/constants.py`.

`constants.py` remains the source of truth for the optimisers, which keeps that
layer free of database access and therefore unit-testable without a Postgres.
These tables mirror those constants so the API can expose them (dropdowns,
presets, validation ranges) and so an analyst can see the rates the costing runs
on.

Idempotent: safe to run on every startup. Existing rows are updated in place
rather than duplicated, so revising a freight rate in constants.py propagates on
the next boot.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    TeaDensityRef,
    PackagingMaterialRef,
    PackageTypeRef,
    PackageWeightRef,
    BoardGradeRef,
    ContainerSpec,
    PalletSpec,
    new_uuid,
)
from app.optimizers.constants import (
    PALLET_TYPES,
    DEFAULT_PALLET_TYPE,
    TEA_DENSITY,
    MATERIALS,
    BOARD_GRADES,
    BOARD_COST_PER_SQM,
    CONTAINERS,
    PACKAGE_WEIGHTS_G,
    DEFAULT_PACKAGE_WEIGHT_G,
    PALLET_L_MM,
    PALLET_W_MM,
    PALLET_H_MM,
    PALLET_MAX_LOAD,
    PALLET_MAX_STACK_MM,
    PALLET_TARE_KG,
)

logger = logging.getLogger(__name__)

PACKAGE_TYPES = {
    "square": (
        "Square / Rectangular Pouch",
        "Rectangular prism. Stacks without void space, so it is usually the "
        "cheaper choice per unit of tea shipped.",
    ),
    "round": (
        "Round / Cylindrical Canister",
        "Cylinder. Premium shelf presence, but circles cannot tile a rectangle: "
        "roughly 21% of the carton cavity is unavoidably air.",
    ),
}


async def _upsert(session: AsyncSession, model, key_field: str, key_value, values: dict) -> None:
    """Insert a row, or update it in place if the natural key already exists."""
    existing = await session.execute(
        select(model).where(getattr(model, key_field) == key_value)
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(model(id=new_uuid(), **{key_field: key_value}, **values))
    else:
        for k, v in values.items():
            setattr(row, k, v)


async def seed_reference_data(session: AsyncSession) -> None:
    """Populate every reference table. Idempotent."""
    for tea_type, spec in TEA_DENSITY.items():
        await _upsert(
            session,
            TeaDensityRef,
            "tea_type",
            tea_type,
            {
                "min_density": spec["min"],
                "max_density": spec["max"],
                "typical_density": spec["typical"],
            },
        )

    for key, spec in MATERIALS.items():
        await _upsert(
            session,
            PackagingMaterialRef,
            "key",
            key,
            {
                "name": spec["name"],
                "cost_per_sqm": spec["cost_per_sqm"],
                "thickness_mm": spec["thickness_mm"],
                "density_g_cm3": spec["density_g_cm3"],
                "eco_score": spec["eco_score"],
            },
        )

    for key, (name, description) in PACKAGE_TYPES.items():
        await _upsert(
            session, PackageTypeRef, "key", key, {"name": name, "description": description}
        )

    for order, spec in enumerate(PACKAGE_WEIGHTS_G):
        await _upsert(
            session,
            PackageWeightRef,
            "grams",
            spec["grams"],
            {
                "label": spec["label"],
                "is_default": spec["grams"] == DEFAULT_PACKAGE_WEIGHT_G,
                "sort_order": order,
            },
        )

    for spec in BOARD_GRADES:
        await _upsert(
            session,
            BoardGradeRef,
            "grade",
            spec["grade"],
            {
                # float('inf') is not representable in Postgres double precision.
                "max_weight_kg": min(spec["max_weight_kg"], 1e6),
                "thickness_mm": spec["thickness_mm"],
                "gsm": spec["gsm"],
                "cost_per_sqm": BOARD_COST_PER_SQM.get(spec["grade"], 35.0),
            },
        )

    for key, spec in CONTAINERS.items():
        await _upsert(
            session,
            ContainerSpec,
            "container_type",
            key,
            {
                "name": spec["name"],
                "internal_length_m": spec["internal_l"],
                "internal_width_m": spec["internal_w"],
                "internal_height_m": spec["internal_h"],
                "volume_m3": spec["volume_m3"],
                "max_payload_kg": spec["max_payload_kg"],
                "tare_kg": spec["tare_kg"],
                "freight_factor": spec["freight_factor"],
            },
        )

    for key, spec in PALLET_TYPES.items():
        await _upsert(
            session,
            PalletSpec,
            "key",
            key,
            {
                "name": spec["name"],
                "length_mm": spec["length_mm"],
                "width_mm": spec["width_mm"],
                "height_mm": spec["deck_mm"],
                "max_load_kg": spec["max_load_kg"],
                "max_stack_height_mm": PALLET_MAX_STACK_MM,
                "tare_kg": spec["tare_kg"],
            },
        )
    # Remove rows for pallet types that no longer exist (e.g. the old "EUR" key),
    # so the reference endpoint never offers a pallet the engine cannot resolve.
    from sqlalchemy import delete as _delete

    await session.execute(
        _delete(PalletSpec).where(PalletSpec.key.notin_(list(PALLET_TYPES)))
    )

    logger.info("Reference data seeded")
