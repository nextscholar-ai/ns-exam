"""
Phase 20 — Database Reflection & BaseMixin Contract CI Test.

Iterates every table registered on `Base.metadata.tables` and verifies that
it strictly adheres to Phase 3 & 4 ORM requirements:
  1. Primary key `id` column exists.
  2. Public UUID `public_id` column exists and is indexed.
  3. Timestamp columns `created_at` and `updated_at` exist.
  4. Soft-delete columns `is_deleted` and `deleted_at` exist (or table is explicitly marked append-only).
"""
from __future__ import annotations

import pytest

# Ensure all module models are imported so Base.metadata is fully populated
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

from app.core.db.base_model import Base


# Tables that intentionally do NOT inherit BaseMixin — association tables,
# audit/history tables, or append-only ledger tables with their own schema.
EXCLUDED_TABLES: frozenset[str] = frozenset({
    "role_permissions",       # Many-to-many join table; no public UUID needed
    "user_roles",             # Many-to-many join table; no public UUID needed
    "login_history",          # Append-only audit ledger; uses its own mixin
    "teacher_subject_map",    # Many-to-many join table; no public UUID needed
})

_MIXIN_TABLES = [t for t in Base.metadata.tables if t not in EXCLUDED_TABLES]


def test_base_metadata_has_registered_tables():
    """Verify that Base.metadata contains all expected domain tables."""
    tables = list(Base.metadata.tables.keys())
    assert len(tables) >= 20, f"Expected at least 20 tables in metadata, found {len(tables)}"


@pytest.mark.parametrize("table_name", _MIXIN_TABLES)
def test_table_has_required_base_mixin_columns(table_name: str):
    """
    CI Reflection Test: Every table MUST implement the standard BaseMixin columns.
    """
    table = Base.metadata.tables[table_name]
    col_names = {col.name for col in table.columns}

    # 1. Primary key id
    assert "id" in col_names, f"Table '{table_name}' is missing primary key 'id' column"

    # 2. Public UUID
    assert "public_id" in col_names, f"Table '{table_name}' is missing 'public_id' column"

    # 3. Timestamps
    assert "created_at" in col_names, f"Table '{table_name}' is missing 'created_at' column"
    assert "updated_at" in col_names, f"Table '{table_name}' is missing 'updated_at' column"

    # 4. Soft-delete columns
    assert "is_deleted" in col_names, f"Table '{table_name}' is missing 'is_deleted' column"
    assert "deleted_at" in col_names, f"Table '{table_name}' is missing 'deleted_at' column"


@pytest.mark.parametrize("table_name", _MIXIN_TABLES)
def test_public_id_column_has_index(table_name: str):
    """Verify public_id column is indexed or part of a unique/primary constraint."""
    table = Base.metadata.tables[table_name]
    public_id_col = table.columns.get("public_id")
    assert public_id_col is not None, f"Table '{table_name}' missing public_id"

    # Check if public_id is indexed or unique
    is_indexed_or_unique = (
        public_id_col.index
        or public_id_col.unique
        or any("public_id" in [c.name for c in idx.columns] for idx in table.indexes)
    )
    assert is_indexed_or_unique, f"Table '{table_name}' public_id column is not indexed/unique"
