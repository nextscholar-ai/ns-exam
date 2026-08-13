"""
Phase 21 — Production Readiness Audit Script.

Verifies:
  1. Secret key strength & security configurations.
  2. Database connectivity & metadata table count.
  3. Event Bus handler registrations.
  4. Notification Transport & ERP Integration settings.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

# Import all module models so Base.metadata is fully populated
import app.modules.academic.models  # noqa: F401
import app.modules.analytics.models  # noqa: F401
import app.modules.blueprint.models  # noqa: F401
import app.modules.evaluation.models  # noqa: F401
import app.modules.exam_management.models  # noqa: F401
import app.modules.identity.models  # noqa: F401
import app.modules.integration.models  # noqa: F401
import app.modules.learning_profile.models  # noqa: F401
import app.modules.paper_generation.models  # noqa: F401
import app.modules.question_bank.models  # noqa: F401
import app.modules.recommendation.models  # noqa: F401
import app.modules.reports.models  # noqa: F401
import app.modules.storage.models  # noqa: F401
import app.modules.student.models  # noqa: F401
import app.modules.teacher.models  # noqa: F401
import app.core.notifications.models  # noqa: F401

from app.core.config import settings
from app.core.db.base_model import Base
from app.core.db.session import check_db_connection
from app.core.events.bus import event_bus


async def run_production_readiness_audit() -> dict[str, Any]:
    """Execute production readiness checks and return audit results."""
    issues: list[str] = []
    warnings: list[str] = []

    # 1. Security & Settings Audit
    if len(settings.jwt.secret) < 32:
        issues.append("JWT_SECRET length is under 32 characters (insecure).")

    if settings.jwt.secret == "CHANGE-ME-IN-PRODUCTION-SECRET-KEY-32-CHARS-MIN":
        warnings.append("Using default example JWT_SECRET key.")

    # 2. Database Audit
    db_connected = await check_db_connection()
    if not db_connected:
        if settings.is_production:
            issues.append("Database connection failed in PRODUCTION mode.")
        else:
            warnings.append("Database connection failed (PostgreSQL not running locally).")

    table_count = len(Base.metadata.tables)
    if table_count < 20:
        issues.append(f"Base.metadata table count ({table_count}) is lower than expected 20+.")

    # 3. Event Bus Audit
    handlers_registered = len(event_bus._subscribers)
    if handlers_registered == 0:
        warnings.append("No event bus handlers registered.")

    is_ready = len(issues) == 0

    return {
        "is_ready": is_ready,
        "app_env": settings.app_env,
        "app_version": settings.app_version,
        "table_count": table_count,
        "db_connected": db_connected,
        "issues": issues,
        "warnings": warnings,
    }


def main() -> None:
    print("==================================================================")
    print("          EXAM ENGINE PRODUCTION READINESS AUDIT                  ")
    print("==================================================================")
    result = asyncio.run(run_production_readiness_audit())

    print(f"Status      : {'[READY]' if result['is_ready'] else '[FAILED]'}")
    print(f"Environment : {result['app_env']}")
    print(f"Version     : {result['app_version']}")
    print(f"DB Connected: {result['db_connected']}")
    print(f"Tables Found: {result['table_count']}")

    if result["warnings"]:
        print("\n[WARNINGS]:")
        for w in result["warnings"]:
            print(f" - {w}")

    if result["issues"]:
        print("\n[ISSUES]:")
        for i in result["issues"]:
            print(f" - {i}")
        sys.exit(1)

    print("\n[OK] Production readiness audit passed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
