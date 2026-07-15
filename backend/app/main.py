"""
Tea Packaging Optimization Platform — FastAPI Application.

Entry point for the optimization API server.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base, async_session_factory
from app.routers import simulation, optimization, dashboard, chat, reference
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ensure reference data is present.

    Schema itself is owned by Alembic (`alembic upgrade head`), not by
    `create_all`. Letting the app create its own tables works until the first
    column change, at which point production silently diverges from the models.
    """
    settings = get_settings()
    if settings.auto_create_tables:
        logger.warning(
            "AUTO_CREATE_TABLES is on — creating tables from models. "
            "Use 'alembic upgrade head' outside development."
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        async with async_session_factory() as session:
            await seed_reference_data(session)
            await session.commit()
    except Exception:
        # Reference data is a convenience; a cold DB should not stop the API from
        # booting and serving /health while an operator investigates.
        logger.exception("Reference data seeding failed; continuing startup")

    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="AI-assisted tea packaging optimization — package, carton, pallet, container",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — driven by config so a deployed frontend does not require a code change.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Register routers
    app.include_router(simulation.router)
    app.include_router(optimization.router)
    app.include_router(dashboard.router)
    app.include_router(chat.router)
    app.include_router(reference.router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
