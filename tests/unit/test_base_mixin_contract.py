"""
CI guard (Phase 3 §17 risk mitigation): fails the build if any mapped model
is added later without inheriting BaseMixin's standard columns. Currently
trivially passes since no concrete models exist yet (Phase 1 foundation) -
this activates automatically as modules add real models from Phase 6 onward.
"""
from app.core.db.base_model import Base

REQUIRED_COLUMNS = {"id", "public_id", "created_at", "updated_at", "is_deleted"}


def test_every_mapped_model_has_base_mixin_columns():
    for mapper in Base.registry.mappers:
        model = mapper.class_
        column_names = {c.name for c in mapper.columns}
        missing = REQUIRED_COLUMNS - column_names
        assert not missing, f"{model.__name__} is missing base mixin columns: {missing}"
