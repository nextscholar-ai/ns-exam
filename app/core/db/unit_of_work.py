"""
Unit of Work (Phase 8 §5.3).

Wraps a single `AsyncSession` per request. Multi-repository transactions
(e.g. Evaluation completing -> Learning Profile updating -> Analytics
updating, all one logical operation) share the *same* `UnitOfWork` instance,
passed down explicitly by the orchestrating service - never opening a second
session mid-request.

Background jobs (Phase 17) get their own `UnitOfWork` instance per job
execution, via `unit_of_work_scope()`, separate from any HTTP request
lifecycle.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import AsyncSessionLocal


class UnitOfWork:
    """
    Thin wrapper exposing `.session` to every repository constructed within
    it, plus explicit `commit`/`rollback` for orchestrating services that
    need an intermediate flush point without ending the overall transaction
    (e.g. "flush after creating the Question row so its generated id is
    available for the next repository call, but don't commit until the
    whole request succeeds").
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork, None]:
    """
    FastAPI dependency: `uow: UnitOfWork = Depends(get_unit_of_work)`.

    Same commit/rollback semantics as `core/db/session.py`'s `get_db` - this
    is the *same underlying session*, just handed to services as a
    `UnitOfWork` object instead of a raw `AsyncSession`, so a service that
    orchestrates several repositories has one clearly-named thing to hold
    onto and pass down (Phase 8 §5.3), rather than threading a bare session
    through every method signature.
    """
    async with AsyncSessionLocal() as session:
        uow = UnitOfWork(session)
        try:
            yield uow
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def unit_of_work_scope() -> AsyncGenerator[UnitOfWork, None]:
    """Use outside of request scope (background jobs, Phase 17 - each job
    execution gets its own UnitOfWork, never shared with an HTTP request)."""
    async with AsyncSessionLocal() as session:
        uow = UnitOfWork(session)
        try:
            yield uow
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
