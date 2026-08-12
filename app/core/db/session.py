"""
Async SQLAlchemy engine + session factory.

Every repository/service receives an `AsyncSession` via the `get_db` FastAPI
dependency - no module ever creates its own engine or session.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Re-exported so service.py modules can type-hint the session without
# importing sqlalchemy directly (Phase 8 §8 / import-linter contract).
DbSession = AsyncSession

engine = create_async_engine(
    settings.db.url,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    echo=settings.db.echo,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: `db: AsyncSession = Depends(get_db)`.

    Commits on clean exit, rolls back on exception, always closes the session.
    Services should NOT call commit() themselves for request-scoped work unless
    they need an intermediate flush - the router-level unit of work commits once.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def db_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Use outside of request scope (background jobs, scripts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Used by the /health/db readiness endpoint."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
