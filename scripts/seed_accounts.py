"""
Seed script — creates all user accounts only.

No academic data, no profiles, no permissions. Just users + role assignments.
Roles (SUPER_ADMIN, ADMIN, SCHOOL_ADMIN, TEACHER, STUDENT) are created
automatically if they don't exist.

USAGE
-----
    python -m scripts.seed_accounts

Safe to re-run — skips accounts that already exist (matched by email).
All accounts use the password: password123
"""
from __future__ import annotations

import asyncio

from app.core.db.session import db_session_scope
from app.core.logging import configure_logging, get_logger
from app.core.security.password import hash_password
from app.modules.identity.models import Role, User, UserRole

configure_logging()
logger = get_logger(__name__)

PASSWORD = "password123"

# ────────────────────────────────────────────────────────────
# ROLES — created automatically if missing (no permissions)
# ────────────────────────────────────────────────────────────

ROLES = ["SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT"]

# ────────────────────────────────────────────────────────────
# ACCOUNTS — add/remove entries here as needed
# ────────────────────────────────────────────────────────────

ACCOUNTS = [
    {"email": "superadmin@ns-exam.com", "user_type": "SUPER_ADMIN", "role": "SUPER_ADMIN"},
    {"email": "admin@ns-exam.com",      "user_type": "ADMIN",       "role": "ADMIN"},
    {"email": "schooladmin@ns-exam.com", "user_type": "SCHOOL_ADMIN", "role": "SCHOOL_ADMIN"},
    {"email": "teacher@ns-exam.com",    "user_type": "TEACHER",     "role": "TEACHER"},
    {"email": "student@ns-exam.com",    "user_type": "EXTERNAL_STUDENT", "role": "STUDENT"},
]


async def seed() -> None:
    async with db_session_scope() as session:
        # Ensure roles exist
        role_objs: dict[str, Role] = {}
        for role_name in ROLES:
            from sqlalchemy import select as sa_select

            existing = (
                await session.execute(
                    sa_select(Role).where(Role.name == role_name, Role.is_deleted.is_(False))
                )
            ).first()
            if existing:
                role_objs[role_name] = await session.get(Role, existing.id)
            else:
                role = Role(name=role_name, description=f"{role_name} role")
                session.add(role)
                await session.flush()
                role_objs[role_name] = role
                logger.info("seed.role_created", role=role_name)

        # Create accounts
        created, skipped = [], []

        for acc in ACCOUNTS:
            from sqlalchemy import select as sa_select

            existing = (
                await session.execute(
                    sa_select(User).where(User.email == acc["email"], User.is_deleted.is_(False))
                )
            ).first()
            if existing:
                skipped.append(acc["email"])
                continue

            user = User(
                email=acc["email"],
                password_hash=hash_password(PASSWORD),
                user_type=acc["user_type"],
                auth_source="LOCAL",
                status="ACTIVE",
            )
            session.add(user)
            await session.flush()

            role = role_objs.get(acc["role"])
            if role:
                session.add(UserRole(user_id=user.id, role_id=role.id))

            created.append((acc["role"], acc["email"]))

        await session.flush()

    print("\n" + "=" * 50)
    print("  SEED COMPLETE")
    print("=" * 50)

    if created:
        print(f"\n  Created {len(created)} account(s):")
        for role, email in created:
            print(f"    [{role:14}] {email}")

    if skipped:
        print(f"\n  Skipped {len(skipped)} account(s) already exist:")
        for email in skipped:
            print(f"    {email}")

    print(f"\n  Password for all accounts: {PASSWORD}")
    print("  Change passwords after first login.")
    print()


if __name__ == "__main__":
    asyncio.run(seed())
