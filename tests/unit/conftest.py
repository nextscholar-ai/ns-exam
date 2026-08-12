"""
Async, in-memory SQLite test database (Phase 8 §16 - "a direct DB test").

Uses the same `Base.metadata` as production, just against SQLite instead of
Postgres, made possible by `GUID` (Phase 8 note in `base_model.py`) - a
cross-dialect UUID column type. `StaticPool` keeps the single in-memory
database alive across the multiple connections a test's `AsyncSession` and
setup code each open.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Import every module that currently defines real models so their tables
# register on Base.metadata before create_all().
from app.modules.academic import models as academic_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.student import models as student_models  # noqa: F401
from app.modules.teacher import models as teacher_models  # noqa: F401
from app.core.db.base_model import Base


@pytest.fixture()
async def sqlite_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
