"""
CI guard (Phase 3 §17 risk mitigation): fails the build if any mapped model
is added later without inheriting BaseMixin's standard columns. Pure
association tables (RolePermission, UserRole, TeacherSubjectMap) and the
append-only LoginHistory log are the documented exceptions (Phase 3 §9 /
Phase 4 §6.1) and are excluded by name.
"""
# Import every module's models submodule so they register on Base.registry
# before this test runs.
from app.modules.academic import models as academic_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.student import models as student_models  # noqa: F401
from app.modules.teacher import models as teacher_models  # noqa: F401
from app.core.db.base_model import Base

REQUIRED_COLUMNS = {"id", "public_id", "created_at", "updated_at", "is_deleted"}
EXEMPT_MODELS = {"RolePermission", "UserRole", "TeacherSubjectMap", "LoginHistory"}


def test_every_mapped_model_has_base_mixin_columns():
    checked = 0
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model.__name__ in EXEMPT_MODELS:
            continue
        column_names = {c.name for c in mapper.columns}
        missing = REQUIRED_COLUMNS - column_names
        assert not missing, f"{model.__name__} is missing base mixin columns: {missing}"
        checked += 1
    assert checked > 0, "Expected at least one concrete model to be registered"
