"""
Simulation router — CRUD endpoints for full optimization simulations.
"""

import logging

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
    LoadPlanResponse,
    PlacementResponse,
    BoxDims,
    MaxCapacityResponse,
    MaxCapacityOption,
    MaxCapacityPackage,
    MaxCapacityCarton,
    MaxCapacityPallet,
)
from app.optimizers.joint import fit_rectangles
from app.optimizers.constants import CONTAINERS, PALLET_L_MM, PALLET_W_MM, PALLET_H_MM
from app.services.simulation_service import run_full_pipeline
from app.services.ai_service import analyze_results

logger = logging.getLogger(__name__)

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

        # Commit before returning. Reporting `201 {id}` while the transaction is
        # still open is a promise the database has not made yet: the frontend
        # redirects straight to /results/{id}, and that GET would 404.
        await db.commit()

        return SimulationCreateResponse(
            id=str(sim.id),
            status=SimulationStatus.completed,
            message="Optimization completed successfully",
        )

    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        # Don't echo str(e): it can carry internals into a client response.
        logger.exception("Simulation failed")
        raise HTTPException(status_code=500, detail="Optimization failed")


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


@router.get("/simulation/{simulation_id}/layout", response_model=LoadPlanResponse)
async def get_load_plan(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """
    The load plan for the recommended container — what goes where.

    Recomputed from the stored dimensions rather than persisted: packing is a pure
    function of those dimensions, so recomputing cannot drift from the saved
    result and costs no schema. The recomputed counts are checked against the
    stored ones and a mismatch is an error, not something to paper over — a 3D
    view that disagrees with the numbers beside it is worse than no 3D view.
    """
    result = await db.execute(
        select(Simulation)
        .options(
            selectinload(Simulation.carton_config),
            selectinload(Simulation.pallet_config),
            selectinload(Simulation.container_configs),
        )
        .where(Simulation.id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    carton = sim.carton_config
    pallet = sim.pallet_config
    best = next((c for c in sim.container_configs if c.is_best), None)
    if not carton or not pallet or not best:
        raise HTTPException(
            status_code=400, detail="Simulation has no completed load plan"
        )

    spec = CONTAINERS.get(best.container_type)
    if not spec:
        raise HTTPException(
            status_code=500, detail=f"Unknown container type {best.container_type}"
        )

    # Cartons are stacked by their OUTER dimensions — board has thickness.
    layer = fit_rectangles(carton.length, carton.width, PALLET_L_MM, PALLET_W_MM)
    floor = fit_rectangles(
        PALLET_L_MM, PALLET_W_MM, spec["internal_l"] * 1000, spec["internal_w"] * 1000
    )

    if layer.count != pallet.cartons_per_layer:
        logger.error(
            "Load plan drift for %s: recomputed %d cartons/layer, stored %d",
            simulation_id,
            layer.count,
            pallet.cartons_per_layer,
        )
        raise HTTPException(
            status_code=500,
            detail="Load plan does not reconcile with the stored result",
        )

    return LoadPlanResponse(
        simulation_id=str(sim.id),
        container_type=best.container_type,
        container=BoxDims(
            length_mm=spec["internal_l"] * 1000,
            width_mm=spec["internal_w"] * 1000,
            height_mm=spec["internal_h"] * 1000,
        ),
        pallet=BoxDims(
            length_mm=PALLET_L_MM,
            width_mm=PALLET_W_MM,
            height_mm=pallet.pallet_height * 1000,
        ),
        pallet_base_height_mm=PALLET_H_MM,
        carton=BoxDims(
            length_mm=carton.length, width_mm=carton.width, height_mm=carton.height
        ),
        carton_layer=[
            PlacementResponse(x=p.x, y=p.y, rotated=p.rotated) for p in layer.placements
        ],
        layers=pallet.layers,
        layer_pattern=pallet.layer_pattern or layer.pattern,
        pallet_floor=[
            PlacementResponse(x=p.x, y=p.y, rotated=p.rotated) for p in floor.placements
        ],
        pallet_stack=best.pallet_stack or 1,
        cartons_per_container=best.cartons_per_container,
        pallets_per_container=best.pallets_per_container or floor.count,
        capacity_utilization_pct=best.capacity_utilization_pct,
    )


@router.get("/simulation/{simulation_id}/max-capacity", response_model=MaxCapacityResponse)
async def get_max_capacity(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """
    The most that fits in ONE container of each type, for this simulation's inputs.

    A different question from the one the results page answers. The page shows the
    cheapest way to ship a given quantity; this shows the ceiling — useful for
    quoting ("how much tea can I get in one 40HC?") and capacity planning.

    Recomputed from the stored inputs rather than persisted: the search is
    deterministic, so recomputation cannot drift from the saved result and costs
    no schema. Same reasoning as /layout.

    Note on comparing types: max units is only meaningful *within* a container
    type. A 40HC beats a 20GP because it is a bigger box, not because it packs
    better — `capacity_utilization_pct` is the fair cross-type measure. The
    response says so rather than letting the reader infer an improvement that
    isn't there.
    """
    result = await db.execute(
        select(Simulation)
        .options(selectinload(Simulation.inputs))
        .where(Simulation.id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if not sim.inputs:
        raise HTTPException(status_code=400, detail="Simulation has no inputs")

    i = sim.inputs
    try:
        pipeline = run_full_pipeline(
            tea_density=i.tea_density,
            package_weight=i.package_weight,
            shipment_quantity=i.shipment_quantity,
            shipment_type=i.shipment_type,
            package_shape=i.package_shape,
            packaging_material=i.packaging_material,
            target_market=i.target_market,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not pipeline.max_capacity or not pipeline.max_capacity_by_container:
        raise HTTPException(status_code=500, detail="No capacity result available")

    def to_option(cfg, recommended_type: str) -> MaxCapacityOption:
        c, p, ct, pl = cfg.container, cfg.package, cfg.carton, cfg.pallet
        tea_kg = c.units_per_container * i.package_weight / 1000.0
        # Tea is light, so these loads are almost always capped by space rather
        # than by the container's weight limit. Saying which is genuinely useful.
        limited_by = "weight" if c.payload_kg >= c.max_payload_kg * 0.98 else "volume"
        return MaxCapacityOption(
            container_type=c.container_type,
            is_recommended_type=(c.container_type == recommended_type),
            max_cartons_per_container=c.cartons_per_container,
            max_units_per_container=c.units_per_container,
            max_tea_weight_kg=round(tea_kg, 1),
            capacity_utilization_pct=c.capacity_utilization_pct,
            pallets_per_container=c.pallets_per_container,
            pallet_stack=c.pallet_stack,
            payload_kg=c.payload_kg,
            max_payload_kg=c.max_payload_kg,
            limited_by=limited_by,
            package=MaxCapacityPackage(
                length_mm=p.length_mm,
                width_mm=p.width_mm,
                height_mm=p.height_mm,
                volume_cm3=p.volume_cm3,
                product_volume_cm3=p.product_volume_cm3,
                fill_ratio=p.fill_ratio,
                cost_estimate=p.cost_estimate,
                shape=p.shape,
                material=p.material,
            ),
            carton=MaxCapacityCarton(
                outer_length_mm=ct.outer_length_mm,
                outer_width_mm=ct.outer_width_mm,
                outer_height_mm=ct.outer_height_mm,
                units_per_carton=ct.units_per_carton,
                arrangement="x".join(str(n) for n in ct.arrangement),
                carton_weight_kg=ct.carton_weight_kg,
                board_grade=ct.board_grade,
            ),
            pallet=MaxCapacityPallet(
                cartons_per_layer=pl.cartons_per_layer,
                layers=pl.layers,
                cartons_per_pallet=pl.cartons_per_pallet,
                pallet_height_m=pl.pallet_height_m,
                total_weight_kg=pl.total_weight_kg,
                layer_pattern=pl.layer_pattern,
                footprint_utilization_pct=pl.footprint_utilization_pct,
            ),
            total_cost_for_shipment=cfg.total_cost,
        )

    rec_type = pipeline.best_container.container_type
    options = [
        to_option(pipeline.max_capacity_by_container[t], rec_type)
        for t in ("20GP", "40GP", "40HC")
        if t in pipeline.max_capacity_by_container
    ]

    absolute = pipeline.max_capacity
    same_type = pipeline.max_capacity_by_container[rec_type]
    rec_units = pipeline.best_container.units_per_container
    max_units_same_type = same_type.container.units_per_container
    gain = ((max_units_same_type - rec_units) / rec_units * 100) if rec_units else 0.0
    cost_delta = round(same_type.total_cost - pipeline.total_cost, 2)
    already_maximal = max_units_same_type <= rec_units

    if already_maximal:
        verdict = (
            f"Your recommended plan already fits the most possible into a "
            f"{rec_type} — {rec_units:,} pouches. Nothing packs more in. Fitting "
            f"more per container also means paying less freight, so the cheapest "
            f"plan and the fullest one are usually the same plan."
        )
    else:
        verdict = (
            f"A {rec_type} could hold {max_units_same_type:,} pouches instead of "
            f"{rec_units:,} ({gain:+.1f}%), but that packing costs Rs "
            f"{cost_delta:,.0f} more for this shipment — the denser pouch shape "
            f"uses more material than it saves in freight."
        )

    # Load plan for the max-packed container, embedded rather than served from a
    # second endpoint: the max configuration is recomputed, never stored, and the
    # search that produced it just ran — its pallet/floor recipes are in hand.
    # A separate endpoint would re-run the whole search to rebuild the same data.
    abs_spec = CONTAINERS[absolute.container.container_type]
    layer_placements = absolute.pallet.layer_placements
    floor_placements = absolute.container.floor_placements
    composed = (
        len(layer_placements)
        * absolute.pallet.layers
        * len(floor_placements)
        * absolute.container.pallet_stack
    )
    if composed != absolute.container.cartons_per_container:
        # Same honesty rule as /layout: a 3D view that disagrees with the number
        # printed beside it is worse than no 3D view.
        logger.error(
            "Max-capacity layout drift for %s: composed %d, reported %d",
            simulation_id,
            composed,
            absolute.container.cartons_per_container,
        )
        raise HTTPException(
            status_code=500,
            detail="Max-capacity load plan does not reconcile with its own counts",
        )

    layout = LoadPlanResponse(
        simulation_id=str(sim.id),
        container_type=absolute.container.container_type,
        container=BoxDims(
            length_mm=abs_spec["internal_l"] * 1000,
            width_mm=abs_spec["internal_w"] * 1000,
            height_mm=abs_spec["internal_h"] * 1000,
        ),
        pallet=BoxDims(
            length_mm=PALLET_L_MM,
            width_mm=PALLET_W_MM,
            height_mm=absolute.pallet.pallet_height_m * 1000,
        ),
        pallet_base_height_mm=PALLET_H_MM,
        carton=BoxDims(
            length_mm=absolute.carton.outer_length_mm,
            width_mm=absolute.carton.outer_width_mm,
            height_mm=absolute.carton.outer_height_mm,
        ),
        carton_layer=[
            PlacementResponse(x=p.x, y=p.y, rotated=p.rotated)
            for p in layer_placements
        ],
        layers=absolute.pallet.layers,
        layer_pattern=absolute.pallet.layer_pattern,
        pallet_floor=[
            PlacementResponse(x=p.x, y=p.y, rotated=p.rotated)
            for p in floor_placements
        ],
        pallet_stack=absolute.container.pallet_stack,
        cartons_per_container=absolute.container.cartons_per_container,
        pallets_per_container=absolute.container.pallets_per_container,
        capacity_utilization_pct=absolute.container.capacity_utilization_pct,
    )

    abs_tea = absolute.container.units_per_container * i.package_weight / 1000.0
    return MaxCapacityResponse(
        simulation_id=str(sim.id),
        options=options,
        absolute_max_container_type=absolute.container.container_type,
        absolute_max_units=absolute.container.units_per_container,
        absolute_max_cartons=absolute.container.cartons_per_container,
        absolute_max_tea_weight_kg=round(abs_tea, 1),
        recommended_container_type=rec_type,
        recommended_units_per_container=rec_units,
        max_units_for_recommended_type=max_units_same_type,
        gain_pct=round(gain, 1),
        cost_delta=cost_delta,
        already_maximal=already_maximal,
        verdict=verdict,
        layout=layout,
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

    # Every key here is read by a prompt in ai_service. This dict had drifted
    # from those prompts after the metric rename: it sent `inner_*` carton keys
    # the prompts no longer read and omitted capacity_utilization_pct,
    # pallet_stack, footprint_utilization_pct and baseline_total_cost. The result
    # was the validator declaring a perfectly good container "invalid — packing
    # density not specified". Keep this in step with the prompts.
    carton = sim.carton_config
    pallet = sim.pallet_config
    cs = sim.cost_summary
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
            # `.length/.width/.height` are the OUTER dims; inner is stored
            # separately. The prompts ask for outer, since that is what is stacked.
            "outer_length_mm": carton.length if carton else 0,
            "outer_width_mm": carton.width if carton else 0,
            "outer_height_mm": carton.height if carton else 0,
            "inner_length_mm": carton.inner_length if carton else 0,
            "inner_width_mm": carton.inner_width if carton else 0,
            "inner_height_mm": carton.inner_height if carton else 0,
            "units_per_carton": carton.units_per_carton if carton else 0,
            "carton_weight_kg": carton.carton_weight if carton else 0,
            "board_grade": carton.board_grade if carton else "",
        },
        "pallet": {
            "cartons_per_layer": pallet.cartons_per_layer if pallet else 0,
            "layers": pallet.layers if pallet else 0,
            "cartons_per_pallet": pallet.cartons_per_pallet if pallet else 0,
            "pallet_height_m": pallet.pallet_height if pallet else 0,
            "total_weight_kg": pallet.total_weight if pallet else 0,
            "footprint_utilization_pct": pallet.footprint_utilization_pct if pallet else 0,
            "layer_pattern": pallet.layer_pattern if pallet else "",
        },
        "best_container": {
            "container_type": best_ct.container_type,
            "utilization_pct": best_ct.utilization_pct,
            "capacity_utilization_pct": best_ct.capacity_utilization_pct,
            "containers_needed": best_ct.containers_needed,
            "pallet_stack": best_ct.pallet_stack,
            "total_freight_cost": best_ct.freight_cost,
        },
        "comparison": [
            {
                "parameter_name": cr.parameter_name,
                "current_value": cr.current_value,
                "ai_value": cr.ai_value,
                "improvement_pct": cr.improvement_pct,
                "driver": cr.driver or "",
            }
            for cr in sim.comparison_results
        ],
        "total_cost": cs.total_cost if cs else 0,
        "baseline_total_cost": cs.baseline_total_cost if cs else 0,
        "total_savings": cs.total_savings if cs else 0,
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
