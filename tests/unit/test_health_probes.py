"""
Phase 21 — Production Observability & Health Probes Unit Test Suite.

Verifies:
  1. GET /health/live returns status ALIVE and version.
  2. GET /health/ready returns READY status and component details.
  3. GET /health/metrics returns observability summary metrics.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_liveness_probe(async_client):
    """Verify /health/live returns ALIVE status."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ALIVE"
    assert "version" in data


@pytest.mark.asyncio
async def test_health_readiness_probe(async_client):
    """Verify /health/ready returns status and components dict."""
    response = await async_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("READY", "NOT_READY")
    assert "components" in data
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_health_metrics_probe(async_client):
    """Verify /health/metrics returns observability data."""
    response = await async_client.get("/health/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "app_env" in data
    assert "app_version" in data
    assert "database_connected" in data
