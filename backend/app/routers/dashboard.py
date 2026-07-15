"""
Dashboard router — aggregate stats for the dashboard page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Simulation, SimulationInput, CostSummary, ContainerConfig
from app.schemas import DashboardResponse, SimulationListItem

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Return aggregate statistics for the dashboard."""

    # Total simulations
    total_sims_result = await db.execute(select(func.count(Simulation.id)))
    total_simulations = total_sims_result.scalar() or 0

    # Total savings (sum of all cost_summary.total_savings)
    savings_result = await db.execute(
        select(func.coalesce(func.sum(CostSummary.total_savings), 0.0))
    )
    total_savings = round(savings_result.scalar() or 0.0, 2)

    # Average container utilization (best container per simulation)
    util_result = await db.execute(
        select(func.coalesce(func.avg(ContainerConfig.utilization_pct), 0.0))
        .where(ContainerConfig.is_best == True)
    )
    avg_utilization = round(util_result.scalar() or 0.0, 1)

    # Recent simulations (last 10)
    recent_query = (
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
        .order_by(Simulation.created_at.desc())
        .limit(10)
    )
    recent_result = await db.execute(recent_query)
    recent_rows = recent_result.all()

    recent = [
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
        for row in recent_rows
    ]

    return DashboardResponse(
        total_simulations=total_simulations,
        total_savings=total_savings,
        average_container_utilization=avg_utilization,
        recent_simulations=recent,
    )
