"""
Tea Packaging Optimization Platform — FastAPI Application.

Entry point for the optimization API server.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.routers import simulation, optimization, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: create tables on startup (dev convenience)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(simulation.router)
    app.include_router(optimization.router)
    app.include_router(dashboard.router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
