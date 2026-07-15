"""
Optimization router — individual stage endpoints + compare endpoint.
Run specific optimization stages without persisting to DB.
"""

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
            length_mm=results[0].length_mm,
            width_mm=results[0].width_mm,
            height_mm=results[0].height_mm,
            shape=results[0].shape,
            material=results[0].material,
            fill_ratio=results[0].fill_ratio,
            material_usage_sqm=results[0].material_usage,
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
                length_mm=alt.length_mm,
                width_mm=alt.width_mm,
                height_mm=alt.height_mm,
                shape=alt.shape,
                material=alt.material,
                fill_ratio=alt.fill_ratio,
                material_usage_sqm=alt.material_usage,
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

        best = ContainerConfigResponse(
            id="temp",
            simulation_id="temp",
            container_type=results[0].container_type,
            cartons_per_container=results[0].cartons_per_container,
            utilization_pct=results[0].utilization_pct,
            empty_space_m3=results[0].empty_space_m3,
            total_units=results[0].total_units,
            freight_cost=results[0].total_freight_cost,
            is_best=True,
        )

        alternatives = []
        for alt in results[1:]:
            alternatives.append(ContainerConfigResponse(
                id="temp",
                simulation_id="temp",
                container_type=alt.container_type,
                cartons_per_container=alt.cartons_per_container,
                utilization_pct=alt.utilization_pct,
                empty_space_m3=alt.empty_space_m3,
                total_units=alt.total_units,
                freight_cost=alt.total_freight_cost,
                is_best=False,
            ))

        return ContainerOptimizeResponse(best_container=best, alternatives=alternatives)

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
            )
            for r in result.comparison
        ]

        return CompareResponse(
            simulation_id=body.simulation_id,
            rows=rows,
            packaging_cost_current=result.current.packaging_cost if result.current else 0,
            packaging_cost_ai=result.packaging_cost,
            freight_cost_current=result.current.freight_cost if result.current else 0,
            freight_cost_ai=result.freight_cost,
            total_cost_current=result.current.total_cost if result.current else 0,
            total_cost_ai=result.total_cost,
            total_savings=result.total_savings,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
