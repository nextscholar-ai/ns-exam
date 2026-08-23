"""Integration-test fixtures.

The app's SQLAlchemy engine is a process-wide singleton whose asyncpg
connections get bound to the event loop that created them. pytest-asyncio
gives every test its own loop, so a connection checked out of the pool by one
test is bound to a loop that is already closed by the time the *next* test
runs - which made `check_db_connection()` intermittently report the (reachable)
database as unreachable. Disposing the pool after every test forces a fresh
connection set on the current loop.
"""
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.db.session import engine


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    yield
    await engine.dispose()


@pytest.fixture()
async def api(async_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Short alias for async_client — used by role-based API tests."""
    yield async_client