"""
Async engine, session factory and the request-scoped session dependency.
"""

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # a recycled/dead connection should not surface as a 500
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Request-scoped session. Rolls back on error, always closes.

    It deliberately does NOT commit. A `yield` dependency's exit code runs after
    the response has been handed back, so committing here meant POST /simulation
    returned `201 {id}` *before* the row existed — and a client that immediately
    fetched that id got a 404. The frontend does exactly that: it creates a
    simulation and redirects straight to its results page.

    Writing endpoints therefore commit their own unit of work before returning,
    which is also where the decision belongs: the endpoint knows when its work is
    complete, the dependency does not.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
