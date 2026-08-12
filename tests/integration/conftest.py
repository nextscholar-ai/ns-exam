"""Integration-test fixtures.

The app's SQLAlchemy engine is a process-wide singleton whose asyncpg
connections get bound to the event loop that created them. pytest-asyncio
gives every test its own loop, so a connection checked out of the pool by one
test is bound to a loop that is already closed by the time the *next* test
runs - which made `check_db_connection()` intermittently report the (reachable)
database as unreachable. Disposing the pool after every test forces a fresh
connection set on the current loop.
"""
import pytest

from app.core.db.session import engine


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    yield
    await engine.dispose()