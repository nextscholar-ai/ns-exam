"""Shared pytest fixtures. Integration DB fixtures (test Postgres via
docker-compose) are fully built out in Phase 20 (Testing Strategy)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
