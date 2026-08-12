"""
Seed script: Roles + Permissions (Phase 6 §6.4).

"Roles seeded, not user-editable in v1... role_permissions mapped via a
migration data script, not hardcoded in application logic - so permission
changes are a data change, not a code deploy."

Run with:
    python -m scripts.seed_roles_permissions

Idempotent - safe to run multiple times (skips roles/permissions that already exist).
"""
from __future__ import annotations

import asyncio

from app.core.db.session import db_session_scope
from app.core.logging import configure_logging, get_logger
from app.modules.identity.models import Permission, Role

configure_logging()
logger = get_logger(__name__)

ROLES = ["SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT"]

# Fine-grained permission codes. Grows as each feature module's phase is built
# (Phase 6 §23 risk note) - defined once per module, not invented ad hoc.
PERMISSIONS = [
    ("question.create", "Create a question in the Question Bank"),
    ("question.approve", "Approve a question version"),
    ("exam.publish", "Publish an exam"),
    ("evaluation.subjective.enter", "Enter subjective evaluation marks"),
    ("report.view.school", "View reports scoped to one's own school"),
    ("report.view.board", "View reports scoped to an entire board"),
]

# Which roles get which permissions, by index into PERMISSIONS above.
ROLE_PERMISSION_MAP: dict[str, list[str]] = {
    "TEACHER": ["question.create", "evaluation.subjective.enter", "report.view.school"],
    "SCHOOL_ADMIN": ["exam.publish", "report.view.school"],
    "ADMIN": [code for code, _ in PERMISSIONS],
    "SUPER_ADMIN": [code for code, _ in PERMISSIONS],
}


async def seed() -> None:
    async with db_session_scope() as session:
        role_objs: dict[str, Role] = {}
        for role_name in ROLES:
            existing = (
                await session.execute(
                    Role.__table__.select().where(Role.name == role_name)  # type: ignore[attr-defined]
                )
            ).first()
            if existing:
                logger.info("seed.role_exists", role=role_name)
                continue
            role = Role(name=role_name, description=f"{role_name} role")
            role.permissions = []
            session.add(role)
            role_objs[role_name] = role
        await session.flush()

        permission_objs: dict[str, Permission] = {}
        for code, description in PERMISSIONS:
            existing = (
                await session.execute(
                    Permission.__table__.select().where(Permission.code == code)  # type: ignore[attr-defined]
                )
            ).first()
            if existing:
                continue
            perm = Permission(code=code, description=description)
            session.add(perm)
            permission_objs[code] = perm
        await session.flush()

        # Re-fetch fresh so relationships attach correctly for newly created rows only.
        for role_name, perm_codes in ROLE_PERMISSION_MAP.items():
            role = role_objs.get(role_name)
            if role is None:
                continue
            for code in perm_codes:
                perm = permission_objs.get(code)
                if perm is not None:
                    role.permissions.append(perm)

        logger.info("seed.completed", roles=len(role_objs), permissions=len(permission_objs))


if __name__ == "__main__":
    asyncio.run(seed())
