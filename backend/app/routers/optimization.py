"""
Optimization router — individual stage endpoints + compare endpoint.
Run specific optimization stages without persisting to DB.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import (
    PackageOptimizeRequest,
    PackageOptimizeResponse,
    PackageOptionResponse,
    CartonOptimizeRequest,
    CartonOptimizeResponse,
    CartonConfigResponse,
    PalletOptimizeRequest,
    PalletOptimizeResponse,
    PalletConfigResponse,
    ContainerOptimizeRequest,
    ContainerOptimizeResponse,
    ContainerConfigResponse,
    CompareRequest,
    CompareResponse,
    CompareRow,
)
from app.services.simulation_service import (
    run_package_only,
    run_carton_only,
    run_pallet_only,
    run_container_only,
    run_full_pipeline,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Optimization"])


# ── Package ────────────────────────────────────────────────────────────────────

@router.post("/optimize/package", response_model=PackageOptimizeResponse)
async def optimize_package(body: PackageOptimizeRequest):
    """Run standalone package optimization. Returns best + alternatives."""
    try:
        results = run_package_only(
            tea_density=body.tea_density,
            package_weight=body.package_weight,
            package_shape=body.package_shape.value,
            packaging_material=body.packaging_material.value,
        )

        if not results:
            raise HTTPException(status_code=400, detail="No valid package dimensions found")

        best = PackageOptionResponse(
            id="temp",
            simulation_id="temp",
            volume_cm3=results[0].volume_cm3,
            product_volume_cm3=results[0].product_volume_cm3,
            length_mm=results[0].length_mm,
            width_mm=results[0].width_mm,
            height_mm=results[0].height_mm,
            shape=results[0].shape,
            material=results[0].material,
            fill_ratio=results[0].fill_ratio,
            material_usage_cm2=results[0].material_usage,
            cost_estimate=results[0].cost_estimate,
            is_best=True,
            rank=1,
        )

        alternatives = []
        for i, alt in enumerate(results[1:3], start=2):
            alternatives.append(PackageOptionResponse(
                id="temp",
                simulation_id="temp",
                volume_cm3=alt.volume_cm3,
                product_volume_cm3=alt.product_volume_cm3,
                length_mm=alt.length_mm,
                width_mm=alt.width_mm,
                height_mm=alt.height_mm,
                shape=alt.shape,
                material=alt.material,
                fill_ratio=alt.fill_ratio,
                material_usage_cm2=alt.material_usage,
                cost_estimate=alt.cost_estimate,
                is_best=False,
                rank=i,
            ))

        return PackageOptimizeResponse(best_package=best, alternatives=alternatives)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Carton ─────────────────────────────────────────────────────────────────────

@router.post("/optimize/carton", response_model=CartonOptimizeResponse)
async def optimize_carton(body: CartonOptimizeRequest):
    """Run standalone carton optimization."""
    try:
        result = run_carton_only(
            package_length_mm=body.package_length_mm,
            package_width_mm=body.package_width_mm,
            package_height_mm=body.package_height_mm,
            shipment_quantity=body.shipment_quantity,
            package_weight_g=body.package_weight_g,
        )

        return CartonOptimizeResponse(
            config=CartonConfigResponse(
                id="temp",
                simulation_id="temp",
                length_mm=result.inner_length_mm,
                width_mm=result.inner_width_mm,
                height_mm=result.inner_height_mm,
                units_per_carton=result.units_per_carton,
                carton_weight_kg=result.carton_weight_kg,
                board_grade=result.board_grade,
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pallet ─────────────────────────────────────────────────────────────────────

@router.post("/optimize/pallet", response_model=PalletOptimizeResponse)
async def optimize_pallet(body: PalletOptimizeRequest):
    """Run standalone pallet optimization."""
    try:
        result = run_pallet_only(
            carton_length_mm=body.carton_length_mm,
            carton_width_mm=body.carton_width_mm,
            carton_height_mm=body.carton_height_mm,
            carton_weight_kg=body.carton_weight_kg,
        )

        return PalletOptimizeResponse(
            config=PalletConfigResponse(
                id="temp",
                simulation_id="temp",
                cartons_per_layer=result.cartons_per_layer,
                layers=result.layers,
                cartons_per_pallet=result.cartons_per_pallet,
                pallet_height_m=result.pallet_height_m,
                total_weight_kg=result.total_weight_kg,
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Container ──────────────────────────────────────────────────────────────────

@router.post("/optimize/container", response_model=ContainerOptimizeResponse)
async def optimize_container(body: ContainerOptimizeRequest):
    """Run standalone container optimization. Returns best + alternatives."""
    try:
        results = run_container_only(
            carton_length_mm=body.carton_length_mm,
            carton_width_mm=body.carton_width_mm,
            carton_height_mm=body.carton_height_mm,
            cartons_per_pallet=body.cartons_per_pallet,
            pallet_height_m=body.pallet_height_m,
            shipment_quantity=body.shipment_quantity,
            units_per_carton=body.units_per_carton,
        )

        if not results:
            raise HTTPException(status_code=400, detail="No suitable container found")

        def _to_response(r, is_best: bool) -> ContainerConfigResponse:
            return ContainerConfigResponse(
                id="temp",
                simulation_id="temp",
                container_type=r.container_type,
                pallets_per_container=r.pallets_per_container,
                pallet_stack=1,
                cartons_per_container=r.cartons_per_container,
                units_per_container=r.units_per_container,
                capacity_utilization_pct=r.capacity_utilization_pct,
                empty_space_per_container_m3=r.empty_space_per_container_m3,
                containers_needed=r.containers_needed,
                total_units_shipped=r.total_units_shipped,
                utilization_pct=r.utilization_pct,
                empty_space_total_m3=r.empty_space_total_m3,
                freight_cost=r.total_freight_cost,
                is_best=is_best,
            )

        return ContainerOptimizeResponse(
            best_container=_to_response(results[0], True),
            alternatives=[_to_response(a, False) for a in results[1:]],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Compare ────────────────────────────────────────────────────────────────────

@router.post("/compare", response_model=CompareResponse)
async def compare_scenarios(body: CompareRequest):
    """Run comparison (current vs AI) for given inputs."""
    try:
        result = run_full_pipeline(
            tea_density=body.tea_density,
            package_weight=body.package_weight,
            shipment_quantity=body.ship_quantity,
            current_package_l=body.current_package_length_mm,
            current_package_w=body.current_package_width_mm,
            current_package_h=body.current_package_height_mm,
            current_carton_l=body.current_carton_length_mm,
            current_carton_w=body.current_carton_width_mm,
            current_carton_h=body.current_carton_height_mm,
            current_units_per_carton=body.current_units_per_carton,
            current_cartons_per_pallet=body.current_cartons_per_pallet,
            current_containers=body.current_containers,
            current_packaging_cost=body.current_packaging_cost,
            current_freight_cost=body.current_freight_cost,
        )

        rows = [
            CompareRow(
                parameter_name=r.parameter_name,
                current_value=r.current_value,
                ai_value=r.ai_value,
                improvement_pct=r.improvement_pct,
                unit=r.unit,
                driver=r.driver,
            )
            for r in result.comparison
        ]

        current = result.current
        return CompareResponse(
            simulation_id=body.simulation_id,
            rows=rows,
            packaging_cost_current=current.packaging_cost if current else 0,
            packaging_cost_ai=result.packaging_cost,
            carton_cost_current=current.carton_cost if current else 0,
            carton_cost_ai=result.carton_cost,
            freight_cost_current=current.freight_cost if current else 0,
            freight_cost_ai=result.freight_cost,
            total_cost_current=current.total_cost if current else 0,
            total_cost_ai=result.total_cost,
            total_savings=result.total_savings,
            # Without these the caller gets a savings figure and no way to check
            # what it was measured against.
            baseline_assumptions=list(current.assumptions) if current else [],
            baseline_is_user_supplied=current.is_user_supplied if current else False,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # Don't echo str(e) — it can carry internals into a client response.
        logger.exception("Compare failed")
        raise HTTPException(status_code=500, detail="Comparison failed")
