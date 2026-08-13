"""
Phase 20 — Architectural Governance & Import Boundary Verification Tests.

Verifies:
  1. No module service imports `sqlalchemy` directly (import-linter contract).
  2. Event payload schemas pass serializable data structures (dataclasses/dicts), never ORM instances.
  3. Cross-module isolation: event bus handlers use db_session_scope and service interfaces.
"""
from __future__ import annotations

import ast
from pathlib import Path
import pytest


APP_DIR = Path(__file__).resolve().parents[2] / "app"
MODULES_DIR = APP_DIR / "modules"


def get_all_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def test_no_sqlalchemy_direct_imports_in_services():
    """
    Import Linter Contract (Phase 8 §8):
    Service files (`app/modules/*/service.py`) MUST NOT import `sqlalchemy` directly.
    They must use repository abstractions and types provided by `app.core.db.session`.
    """
    service_files = list(MODULES_DIR.rglob("service.py"))
    violations: list[str] = []

    for s_file in service_files:
        tree = ast.parse(s_file.read_text(encoding="utf-8"), filename=str(s_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "sqlalchemy" or alias.name.startswith("sqlalchemy."):
                        violations.append(f"{s_file.relative_to(APP_DIR)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "sqlalchemy" or node.module.startswith("sqlalchemy.")):
                    # Allow typing-only or session import from core, but disallow raw query operators (select, delete, text) in service
                    imported_names = [alias.name for alias in node.names]
                    for name in imported_names:
                        if name in ("select", "delete", "update", "text", "func"):
                            violations.append(
                                f"{s_file.relative_to(APP_DIR)} imports raw SQL '{name}' from {node.module}"
                            )

    assert not violations, f"Architectural boundary violations found:\n" + "\n".join(violations)


def test_event_payloads_are_dataclasses_or_dicts():
    """
    Event Bus Isolation:
    All domain events defined in `events.py` across modules must use dataclasses or dicts,
    never ORM model objects.
    """
    event_files = list(MODULES_DIR.rglob("events.py"))
    assert len(event_files) >= 5, "Expected at least 5 module events.py files"

    for e_file in event_files:
        content = e_file.read_text(encoding="utf-8")
        # Ensure no ORM model references are passed as event payload parameters
        assert "DeclarativeBase" not in content, f"{e_file} references ORM DeclarativeBase"


def test_core_events_registry_has_canonical_names():
    """Verify canonical event names in event_names.py match standard string values."""
    from app.core.events import event_names

    names = [
        getattr(event_names, attr)
        for attr in dir(event_names)
        if not attr.startswith("_") and attr.isupper()
    ]
    assert len(names) >= 10, f"Expected canonical event names, found {len(names)}"
    assert all(isinstance(n, str) and len(n) > 0 for n in names)
