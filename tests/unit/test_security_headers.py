"""
Phase 21 — Security Headers Middleware Unit Test Suite.

Verifies:
  1. Incoming requests receive all required production security headers.
  2. Security headers are set on both 2xx success and error responses.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_security_headers_present_on_response(async_client):
    """Verify HTTP security response headers on /health."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert "max-age=31536000" in headers.get("Strict-Transport-Security", "")
    assert headers.get("Content-Security-Policy") == "default-src 'self'"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_security_headers_present_on_api_route(async_client):
    """Verify HTTP security response headers on /api/v1/ route."""
    response = await async_client.get("/api/v1/jobs/nonexistent-id")
    assert response.status_code == 404

    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
