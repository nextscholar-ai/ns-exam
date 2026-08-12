"""Shared pytest fixtures. Integration DB fixtures (test Postgres via
docker-compose) are fully built out in Phase 20 (Testing Strategy)."""
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import rate_limiter
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Prevents rate-limit state from one test bleeding into another - the
    limiter is a process-wide singleton (Phase 7 §5.8 v1 in-memory limitation)."""
    rate_limiter.reset()
    yield


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
