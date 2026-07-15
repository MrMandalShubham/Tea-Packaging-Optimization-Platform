"""
Reference router — master data for the form dropdowns.

The brief specifies Package Weight as a dropdown. The options could have been an
array in the React component, but then the SKUs an exporter sells would live in
the browser bundle, separately from the rates the costing runs on, and changing
them would need a redeploy.

They are served from the reference tables instead, which are seeded from
`optimizers/constants.py`. One source of truth, revisable without shipping code.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    PackageWeightRef,
    TeaDensityRef,
    PackagingMaterialRef,
    PackageTypeRef,
    ContainerSpec,
)
from app.optimizers.constants import (
    MAX_PACKAGE_WEIGHT_G,
    MIN_PACKAGE_WEIGHT_G,
    MAX_TEA_DENSITY,
    MIN_TEA_DENSITY,
)
from app.schemas import (
    ReferenceDataResponse,
    PackageWeightOption,
    TeaDensityOption,
    MaterialOption,
    PackageTypeOption,
    ContainerSpecOption,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Reference"])


@router.get("/reference", response_model=ReferenceDataResponse)
async def get_reference_data(db: AsyncSession = Depends(get_db)) -> ReferenceDataResponse:
    """
    Return the master data backing the New Simulation form.

    The numeric bounds travel with the options so the client validates against the
    same limits the API enforces, rather than re-declaring them.
    """
    try:
        weights = (
            await db.execute(select(PackageWeightRef).order_by(PackageWeightRef.sort_order))
        ).scalars().all()
        densities = (
            await db.execute(select(TeaDensityRef).order_by(TeaDensityRef.tea_type))
        ).scalars().all()
        materials = (
            await db.execute(select(PackagingMaterialRef).order_by(PackagingMaterialRef.cost_per_sqm))
        ).scalars().all()
        types = (await db.execute(select(PackageTypeRef).order_by(PackageTypeRef.key))).scalars().all()
        containers = (
            await db.execute(select(ContainerSpec).order_by(ContainerSpec.volume_m3))
        ).scalars().all()
    except Exception:
        logger.exception("Failed to load reference data")
        raise HTTPException(status_code=503, detail="Reference data unavailable")

    return ReferenceDataResponse(
        package_weights=[PackageWeightOption.model_validate(w) for w in weights],
        tea_densities=[TeaDensityOption.model_validate(d) for d in densities],
        materials=[MaterialOption.model_validate(m) for m in materials],
        package_types=[PackageTypeOption.model_validate(t) for t in types],
        containers=[ContainerSpecOption.model_validate(c) for c in containers],
        min_package_weight_g=MIN_PACKAGE_WEIGHT_G,
        max_package_weight_g=MAX_PACKAGE_WEIGHT_G,
        min_tea_density=MIN_TEA_DENSITY,
        max_tea_density=MAX_TEA_DENSITY,
    )
