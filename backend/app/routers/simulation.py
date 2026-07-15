"""
Simulation router — CRUD endpoints for full optimization simulations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    User,
    Simulation,
    SimulationInput,
    PackageOption,
    CartonConfig,
    PalletConfig,
    ContainerConfig,
    ComparisonResult,
    CostSummary,
    new_uuid,
    utcnow,
)
from app.schemas import (
    SimulationCreateRequest,
    SimulationCreateResponse,
    SimulationDetailResponse,
    SimulationListItem,
    PaginatedSimulations,
    SimulationStatus,
    PackageOptionResponse,
    CartonConfigResponse,
    PalletConfigResponse,
    ContainerConfigResponse,
    CompareRow,
    CompareResponse,
    StageValidationResponse,
    AIAnalysisResponse,
)
from app.services.simulation_service import run_full_pipeline
from app.services.ai_service import analyze_results

router = APIRouter(prefix="/api", tags=["Simulations"])


async def _get_or_create_default_user(db: AsyncSession) -> User:
    """Get or create a default system user."""
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=new_uuid(),
            email="system@teaopt.local",
            name="System User",
            created_at=utcnow(),
        )
        db.add(user)
        await db.flush()
    return user


def _model_to_package_response(p: PackageOption) -> PackageOptionResponse:
    return PackageOptionResponse(
        id=str(p.id),
        simulation_id=str(p.simulation_id),
        volume_cm3=p.volume,
        product_volume_cm3=p.product_volume,
        length_mm=p.length,
        width_mm=p.width,
        height_mm=p.height,
        shape=p.shape,
        material=p.material,
        fill_ratio=p.fill_ratio,
        material_usage_cm2=p.material_usage,
        cost_estimate=p.cost_estimate,
        is_best=p.is_best,
        rank=p.rank,
    )


def _model_to_carton_response(c: CartonConfig) -> CartonConfigResponse:
    return CartonConfigResponse(
        id=str(c.id),
        simulation_id=str(c.simulation_id),
        length_mm=c.length,
        width_mm=c.width,
        height_mm=c.height,
        inner_length_mm=c.inner_length,
        inner_width_mm=c.inner_width,
        inner_height_mm=c.inner_height,
        units_per_carton=c.units_per_carton,
        arrangement=c.arrangement,
        carton_weight_kg=c.carton_weight,
        board_grade=c.board_grade,
        board_cost_per_carton=c.board_cost_per_carton,
    )


def _model_to_pallet_response(p: PalletConfig) -> PalletConfigResponse:
    return PalletConfigResponse(
        id=str(p.id),
        simulation_id=str(p.simulation_id),
        cartons_per_layer=p.cartons_per_layer,
        layers=p.layers,
        cartons_per_pallet=p.cartons_per_pallet,
        pallet_height_m=p.pallet_height,
        total_weight_kg=p.total_weight,
        layer_pattern=p.layer_pattern,
        footprint_utilization_pct=p.footprint_utilization_pct,
    )


def _model_to_container_response(c: ContainerConfig) -> ContainerConfigResponse:
    return ContainerConfigResponse(
        id=str(c.id),
        simulation_id=str(c.simulation_id),
        container_type=c.container_type,
        pallets_per_container=c.pallets_per_container,
        pallet_stack=c.pallet_stack,
        cartons_per_container=c.cartons_per_container,
        units_per_container=c.units_per_container,
        capacity_utilization_pct=c.capacity_utilization_pct,
        empty_space_per_container_m3=c.empty_space_per_container_m3,
        containers_needed=c.containers_needed,
        total_units_shipped=c.total_units_shipped,
        utilization_pct=c.utilization_pct,
        empty_space_total_m3=c.empty_space_total_m3,
        payload_kg=c.payload_kg,
        freight_cost=c.freight_cost,
        is_best=c.is_best,
    )


@router.post("/simulation", response_model=SimulationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_simulation(body: SimulationCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create and run a new optimization simulation."""
    try:
        # 1. Get or create user
        user = await _get_or_create_default_user(db)

        # 2. Create simulation record
        sim = Simulation(
            id=new_uuid(),
            user_id=user.id,
            status="running",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(sim)
        await db.flush()

        # 3. Save inputs
        inputs = SimulationInput(
            id=new_uuid(),
            simulation_id=sim.id,
            tea_density=body.tea_density,
            package_weight=body.package_weight,
            shipment_quantity=body.shipment_quantity,
            shipment_type=body.shipment_type.value,
            package_shape=body.package_shape.value,
            packaging_material=body.packaging_material.value,
            target_market=body.target_market,
        )
        db.add(inputs)

        # 4. Run pipeline
        result = run_full_pipeline(
            tea_density=body.tea_density,
            package_weight=body.package_weight,
            shipment_quantity=body.shipment_quantity,
            shipment_type=body.shipment_type.value,
            package_shape=body.package_shape.value,
            packaging_material=body.packaging_material.value,
            target_market=body.target_market,
        )

        # 5. Save package options
        for pkg in [result.best_package] + result.package_alternatives:
            db.add(PackageOption(
                id=new_uuid(),
                simulation_id=sim.id,
                volume=pkg.volume_cm3,
                product_volume=pkg.product_volume_cm3,
                length=pkg.length_mm,
                width=pkg.width_mm,
                height=pkg.height_mm,
                shape=pkg.shape,
                material=pkg.material,
                fill_ratio=pkg.fill_ratio,
                material_usage=pkg.material_usage,
                cost_estimate=pkg.cost_estimate,
                is_best=pkg.is_best,
                rank=pkg.rank,
            ))

        # 6. Save carton config — outer dims are the purchasable spec, inner is
        #    the packing cavity; both matter downstream.
        c = result.carton
        if c:
            db.add(CartonConfig(
                id=new_uuid(),
                simulation_id=sim.id,
                length=c.outer_length_mm,
                width=c.outer_width_mm,
                height=c.outer_height_mm,
                inner_length=c.inner_length_mm,
                inner_width=c.inner_width_mm,
                inner_height=c.inner_height_mm,
                units_per_carton=c.units_per_carton,
                arrangement="x".join(str(n) for n in c.arrangement),
                carton_weight=c.carton_weight_kg,
                board_grade=c.board_grade,
                board_area_m2=c.board_area_m2,
                board_cost_per_carton=c.board_cost_per_carton,
            ))

        # 7. Save pallet config
        p = result.pallet
        if p:
            db.add(PalletConfig(
                id=new_uuid(),
                simulation_id=sim.id,
                cartons_per_layer=p.cartons_per_layer,
                layers=p.layers,
                cartons_per_pallet=p.cartons_per_pallet,
                pallet_height=p.pallet_height_m,
                total_weight=p.total_weight_kg,
                layer_pattern=p.layer_pattern,
                footprint_utilization_pct=p.footprint_utilization_pct,
            ))

        # 8. Save one container row per type (Module 6's 20GP/40GP/40HC compare).
        #    Keying by type also honours the uq_sim_container constraint — the
        #    joint search can return several configs sharing a container type.
        for ct_key, cfg in result.configurations_by_container.items():
            ct = cfg.container
            db.add(ContainerConfig(
                id=new_uuid(),
                simulation_id=sim.id,
                container_type=ct.container_type,
                pallets_per_container=ct.pallets_per_container,
                pallet_stack=ct.pallet_stack,
                cartons_per_container=ct.cartons_per_container,
                units_per_container=ct.units_per_container,
                capacity_utilization_pct=ct.capacity_utilization_pct,
                empty_space_per_container_m3=ct.empty_space_per_container_m3,
                containers_needed=ct.containers_needed,
                total_units_shipped=ct.total_units_shipped,
                utilization_pct=ct.utilization_pct,
                empty_space_total_m3=ct.empty_space_total_m3,
                payload_kg=ct.payload_kg,
                freight_cost=ct.total_freight_cost,
                is_best=cfg.is_best,
            ))

        # 9. Save comparison results
        for row in result.comparison:
            db.add(ComparisonResult(
                id=new_uuid(),
                simulation_id=sim.id,
                parameter_name=row.parameter_name,
                current_value=row.current_value,
                ai_value=row.ai_value,
                improvement_pct=row.improvement_pct,
                unit=row.unit,
                driver=row.driver,
            ))

        # 10. Save cost summary — both sides stored explicitly
        base = result.current
        db.add(CostSummary(
            id=new_uuid(),
            simulation_id=sim.id,
            packaging_cost=result.packaging_cost,
            carton_cost=result.carton_cost,
            freight_cost=result.freight_cost,
            total_cost=result.total_cost,
            baseline_packaging_cost=base.packaging_cost if base else 0.0,
            baseline_carton_cost=base.carton_cost if base else 0.0,
            baseline_freight_cost=base.freight_cost if base else 0.0,
            baseline_total_cost=base.total_cost if base else 0.0,
            baseline_assumptions="\n".join(base.assumptions) if base else None,
            baseline_is_user_supplied=base.is_user_supplied if base else False,
            total_savings=result.total_savings,
        ))

        # 11. Update status to completed
        sim.status = "completed"
        sim.updated_at = utcnow()

        await db.flush()

        return SimulationCreateResponse(
            id=str(sim.id),
            status=SimulationStatus.completed,
            message="Optimization completed successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.get("/simulation", response_model=PaginatedSimulations)
async def list_simulations(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all simulations with pagination."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    # Count total
    count_result = await db.execute(select(func.count(Simulation.id)))
    total = count_result.scalar() or 0

    # Query with joins
    query = (
        select(
            Simulation.id,
            Simulation.status,
            Simulation.created_at,
            Simulation.updated_at,
            SimulationInput.tea_density,
            SimulationInput.package_weight,
            SimulationInput.shipment_quantity,
            CostSummary.total_cost,
            CostSummary.total_savings,
        )
        .outerjoin(SimulationInput, SimulationInput.simulation_id == Simulation.id)
        .outerjoin(CostSummary, CostSummary.simulation_id == Simulation.id)
        .order_by(desc(Simulation.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows_result = await db.execute(query)
    rows = rows_result.all()

    items = [
        SimulationListItem(
            id=str(row[0]),
            status=row[1],
            created_at=row[2],
            updated_at=row[3],
            tea_density=row[4],
            package_weight=row[5],
            shipment_quantity=row[6],
            total_cost=row[7],
            total_savings=row[8],
        )
        for row in rows
    ]

    return PaginatedSimulations(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/simulation/{simulation_id}", response_model=SimulationDetailResponse)
async def get_simulation(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single simulation with all optimization results."""
    # Load simulation with all relations
    result = await db.execute(
        select(Simulation)
        .options(
            selectinload(Simulation.inputs),
            selectinload(Simulation.package_options),
            selectinload(Simulation.carton_config),
            selectinload(Simulation.pallet_config),
            selectinload(Simulation.container_configs),
            selectinload(Simulation.comparison_results),
            selectinload(Simulation.cost_summary),
        )
        .where(Simulation.id == simulation_id)
    )
    sim = result.scalar_one_or_none()

    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Build response
    inputs = None
    if sim.inputs:
        inputs = SimulationCreateRequest(
            tea_density=sim.inputs.tea_density,
            package_weight=sim.inputs.package_weight,
            shipment_quantity=sim.inputs.shipment_quantity,
            shipment_type=sim.inputs.shipment_type,
            package_shape=sim.inputs.package_shape,
            packaging_material=sim.inputs.packaging_material,
            target_market=sim.inputs.target_market,
        )

    # Package options
    packages = sorted(sim.package_options, key=lambda x: x.rank)
    best_pkg = None
    alternatives = []
    for pkg in packages:
        resp = _model_to_package_response(pkg)
        if pkg.is_best:
            best_pkg = resp
        else:
            alternatives.append(resp)

    # Carton
    carton_resp = _model_to_carton_response(sim.carton_config) if sim.carton_config else None

    # Pallet
    pallet_resp = _model_to_pallet_response(sim.pallet_config) if sim.pallet_config else None

    # Containers
    containers = sorted(sim.container_configs, key=lambda x: (not x.is_best, x.id))
    best_container = None
    container_alts = []
    for ct in containers:
        resp = _model_to_container_response(ct)
        if ct.is_best:
            best_container = resp
        else:
            container_alts.append(resp)

    # Comparison — baseline figures are read back from their own columns. The
    # previous version reconstructed them as (cost − total_savings), which
    # subtracted the whole shipment's saving from each individual cost line and
    # so reported a different baseline on every row.
    comparison = None
    if sim.comparison_results:
        rows = [
            CompareRow(
                parameter_name=cr.parameter_name,
                current_value=cr.current_value,
                ai_value=cr.ai_value,
                improvement_pct=cr.improvement_pct,
                unit=cr.unit or "",
                driver=cr.driver or "",
            )
            for cr in sim.comparison_results
        ]
        cs = sim.cost_summary
        comparison = CompareResponse(
            simulation_id=str(sim.id),
            rows=rows,
            packaging_cost_current=cs.baseline_packaging_cost if cs else 0,
            packaging_cost_ai=cs.packaging_cost if cs else 0,
            carton_cost_current=cs.baseline_carton_cost if cs else 0,
            carton_cost_ai=cs.carton_cost if cs else 0,
            freight_cost_current=cs.baseline_freight_cost if cs else 0,
            freight_cost_ai=cs.freight_cost if cs else 0,
            total_cost_current=cs.baseline_total_cost if cs else 0,
            total_cost_ai=cs.total_cost if cs else 0,
            total_savings=cs.total_savings if cs else 0,
            baseline_assumptions=(
                cs.baseline_assumptions.split("\n") if cs and cs.baseline_assumptions else []
            ),
            baseline_is_user_supplied=cs.baseline_is_user_supplied if cs else False,
        )

    return SimulationDetailResponse(
        id=str(sim.id),
        status=sim.status,
        created_at=sim.created_at,
        updated_at=sim.updated_at,
        inputs=inputs,
        best_package=best_pkg,
        package_alternatives=alternatives,
        carton=carton_resp,
        pallet=pallet_resp,
        best_container=best_container,
        container_alternatives=container_alts,
        comparison=comparison,
    )


@router.get("/simulation/{simulation_id}/ai", response_model=AIAnalysisResponse)
async def get_ai_analysis(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """Run AI validation and explanation on a completed simulation."""
    # Load simulation
    result = await db.execute(
        select(Simulation)
        .options(
            selectinload(Simulation.inputs),
            selectinload(Simulation.package_options),
            selectinload(Simulation.carton_config),
            selectinload(Simulation.pallet_config),
            selectinload(Simulation.container_configs),
            selectinload(Simulation.comparison_results),
            selectinload(Simulation.cost_summary),
        )
        .where(Simulation.id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Build data dict for AI
    best_pkg = None
    for p in sorted(sim.package_options, key=lambda x: x.rank):
        if p.is_best:
            best_pkg = p
            break

    best_ct = None
    for c in sim.container_configs:
        if c.is_best:
            best_ct = c
            break

    if not best_pkg or not best_ct:
        raise HTTPException(status_code=400, detail="Simulation has no optimization results")

    pipeline_data = {
        "tea_density": sim.inputs.tea_density if sim.inputs else 0,
        "package_weight": sim.inputs.package_weight if sim.inputs else 0,
        "shipment_quantity": sim.inputs.shipment_quantity if sim.inputs else 0,
        "best_package": {
            "length_mm": best_pkg.length,
            "width_mm": best_pkg.width,
            "height_mm": best_pkg.height,
            "volume_cm3": best_pkg.volume,
            "fill_ratio": best_pkg.fill_ratio,
            "material": best_pkg.material,
            "shape": best_pkg.shape,
        },
        "carton": {
            "inner_length_mm": sim.carton_config.length if sim.carton_config else 0,
            "inner_width_mm": sim.carton_config.width if sim.carton_config else 0,
            "inner_height_mm": sim.carton_config.height if sim.carton_config else 0,
            "units_per_carton": sim.carton_config.units_per_carton if sim.carton_config else 0,
            "carton_weight_kg": sim.carton_config.carton_weight if sim.carton_config else 0,
            "board_grade": sim.carton_config.board_grade if sim.carton_config else "",
        },
        "pallet": {
            "cartons_per_layer": sim.pallet_config.cartons_per_layer if sim.pallet_config else 0,
            "layers": sim.pallet_config.layers if sim.pallet_config else 0,
            "cartons_per_pallet": sim.pallet_config.cartons_per_pallet if sim.pallet_config else 0,
            "pallet_height_m": sim.pallet_config.pallet_height if sim.pallet_config else 0,
            "total_weight_kg": sim.pallet_config.total_weight if sim.pallet_config else 0,
        },
        "best_container": {
            "container_type": best_ct.container_type,
            "utilization_pct": best_ct.utilization_pct,
            "containers_needed": best_ct.containers_needed,
            "total_freight_cost": best_ct.freight_cost,
        },
        "comparison": [
            {
                "parameter_name": cr.parameter_name,
                "current_value": cr.current_value,
                "ai_value": cr.ai_value,
                "improvement_pct": cr.improvement_pct,
            }
            for cr in sim.comparison_results
        ],
        "total_cost": sim.cost_summary.total_cost if sim.cost_summary else 0,
        "total_savings": sim.cost_summary.total_savings if sim.cost_summary else 0,
    }

    analysis = await analyze_results(pipeline_data)

    return AIAnalysisResponse(
        validations=[
            StageValidationResponse(stage=v.stage, status=v.status, message=v.message)
            for v in analysis.validations
        ],
        summary=analysis.summary,
        error=analysis.error,
    )
