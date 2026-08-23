"""
Phase 20 — API Response Envelope & Error Contract Integration Tests.

Verifies:
  1. Success responses follow standard envelope `{"success": true, "data": ..., "meta": {"request_id": ..., "timestamp": ...}}`.
  2. Error responses follow standard envelope `{"success": false, "error": {"code": ..., "message": ...}, "meta": {...}}`.
  3. Health endpoints `/health` and `/health/db` return expected payloads.
  4. Non-existent routes return standard 404 envelope.
"""
from __future__ import annotations

import pytest

from .test_helpers import auth_header, super_admin_token


@pytest.mark.asyncio
async def test_health_endpoint_response_format(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_db_endpoint_response_format(async_client):
    response = await async_client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_api_v1_envelope_success_format(async_client):
    """Endpoints under /api/v1/ wrap success response in envelope."""
    response = await async_client.get("/api/v1/academic/boards")
    assert response.status_code == 200
    json_data = response.json()

    assert "success" in json_data
    assert json_data["success"] is True
    assert "data" in json_data
    assert "meta" in json_data
    assert "request_id" in json_data["meta"]
    assert "timestamp" in json_data["meta"]


@pytest.mark.asyncio
async def test_api_v1_envelope_error_format_404(async_client):
    """Domain NotFoundError under /api/v1/ returns standard error envelope."""
    token = super_admin_token()
    response = await async_client.get(
        "/api/v1/jobs/nonexistent-job-id-999",
        headers=auth_header(token),
    )
    assert response.status_code == 404
    json_data = response.json()

    assert "success" in json_data
    assert json_data["success"] is False
    assert "error" in json_data
    assert "message" in json_data["error"]
    assert "meta" in json_data


@pytest.mark.asyncio
async def test_jobs_list_response_envelope(async_client):
    """GET /api/v1/jobs/ returns list response inside standard envelope."""
    token = super_admin_token()
    response = await async_client.get(
        "/api/v1/jobs/",
        headers=auth_header(token),
    )
    assert response.status_code == 200
    json_data = response.json()

    assert json_data["success"] is True
    assert isinstance(json_data["data"], list)
