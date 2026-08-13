"""
Phase 21 — Production Readiness Script Integration Test.

Verifies:
  1. `run_production_readiness_audit()` executes without exceptions.
  2. Audit returns structured status payload with issues and warnings list.
"""
from __future__ import annotations

import pytest

from scripts.verify_production_readiness import run_production_readiness_audit


@pytest.mark.asyncio
async def test_production_readiness_audit_execution(sqlite_session):
    """Verify production readiness audit script returns valid result payload."""
    result = await run_production_readiness_audit()

    assert "is_ready" in result
    assert "app_env" in result
    assert "app_version" in result
    assert "table_count" in result
    assert result["table_count"] >= 20
    assert isinstance(result["issues"], list)
    assert isinstance(result["warnings"], list)
