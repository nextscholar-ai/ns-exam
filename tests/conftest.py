"""
Shared pytest fixtures for unit and integration test suites (Phase 20).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Import every module that defines ORM models so Base.metadata is complete
from app.modules.academic import models as academic_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.student import models as student_models  # noqa: F401
from app.modules.teacher import models as teacher_models  # noqa: F401
from app.modules.storage import models as storage_models  # noqa: F401
from app.modules.question_bank import models as question_bank_models  # noqa: F401
from app.modules.blueprint import models as blueprint_models  # noqa: F401
from app.modules.paper_generation import models as paper_generation_models  # noqa: F401
from app.modules.exam_management import models as exam_management_models  # noqa: F401
from app.modules.evaluation import models as evaluation_models  # noqa: F401
from app.modules.learning_profile import models as learning_profile_models  # noqa: F401
from app.modules.recommendation import models as recommendation_models  # noqa: F401
from app.modules.analytics import models as analytics_models  # noqa: F401
from app.modules.reports import models as reports_models  # noqa: F401
from app.modules.integration import models as integration_models  # noqa: F401
from app.core.notifications import models as notification_models  # noqa: F401
from app.core.db.base_model import Base
from app.core.rate_limit import rate_limiter
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Prevents rate-limit state from one test bleeding into another."""
    rate_limiter.reset()
    yield


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client fixture built with ASGITransport.
    Overrides the `get_db` dependency with an in-memory SQLite session so
    API contract tests work without a real PostgreSQL database.
    """
    from app.core.db.session import get_db

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.fixture()
async def sqlite_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite database session fixture shared by unit & integration tests."""
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
