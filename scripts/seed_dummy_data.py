"""
Seed dummy data for local testing: accounts + academic snapshot tree +
student/teacher profiles. Idempotent - safe to re-run.

Run with:
    python -m scripts.seed_dummy_data

Creates:
  - 5 login accounts (SUPER_ADMIN / ADMIN / SCHOOL_ADMIN / TEACHER / STUDENT)
  - Academic snapshot tree: Board -> School -> AcademicSession -> Class ->
    Subject -> Chapter -> Unit -> Topic (all ERP-owned, SYNCED)
  - One StudentProfile + one TeacherProfile linked to the school

Credentials (all use password: password123):
  superadmin@ns-exam.com   / password123   (SUPER_ADMIN)
  admin@ns-exam.com        / password123   (ADMIN)
  schooladmin@ns-exam.com  / password123   (SCHOOL_ADMIN)
  teacher@ns-exam.com      / password123   (TEACHER)
  student@ns-exam.com      / password123   (STUDENT)
"""
from __future__ import annotations

import asyncio
from datetime import date

from app.core.db.session import db_session_scope
from app.core.logging import configure_logging, get_logger
from app.core.security.password import hash_password
from app.modules.academic.models import (
    AcademicSession,
    Board,
    Chapter,
    Class,
    School,
    Subject,
    Topic,
    Unit,
)
from app.modules.identity.models import Company, Role, User, UserRole
from app.modules.student.models import StudentProfile
from app.modules.teacher.models import TeacherProfile, TeacherSubjectMap

configure_logging()
logger = get_logger(__name__)

PASSWORD = "password123"


async def seed() -> None:
    async with db_session_scope() as session:
        # ---- Company (single-tenant root) --------------------------------
        company = (
            await session.execute(Company.__table__.select().limit(1))  # type: ignore[attr-defined]
        ).first()
        if company is None:
            session.add(Company(name="NS Exam Engine"))
            logger.info("seed.dummy.company")
        else:
            logger.info("seed.dummy.company_exists")

        # ---- Academic snapshot tree (ERP-owned, SYNCED) -------------------
        board = (
            await session.execute(Board.__table__.select().where(Board.erp_id == "ERP_BOARD_CBSE"))
        ).first()
        if board is None:
            board = Board(name="CBSE", code="CBSE", erp_id="ERP_BOARD_CBSE", status="ACTIVE")
            session.add(board)
            await session.flush()
            logger.info("seed.dummy.board", erp_id=board.erp_id)
        else:
            logger.info("seed.dummy.board_exists", erp_id="ERP_BOARD_CBSE")

        school = (
            await session.execute(School.__table__.select().where(School.erp_id == "ERP_SCHOOL_GVH"))
        ).first()
        if school is None:
            school = School(
                board_id=board.id,
                name="Green Valley High",
                erp_id="ERP_SCHOOL_GVH",
                status="ACTIVE",
            )
            session.add(school)
            await session.flush()
            logger.info("seed.dummy.school", erp_id=school.erp_id)
        else:
            logger.info("seed.dummy.school_exists", erp_id="ERP_SCHOOL_GVH")

        session_row = (
            await session.execute(
                AcademicSession.__table__.select().where(
                    AcademicSession.erp_id == "ERP_SES_2627"
                )
            )
        ).first()
        if session_row is None:
            session_row = AcademicSession(
                school_id=school.id,
                name="2026-27",
                start_date=date(2026, 4, 1),
                end_date=date(2027, 3, 31),
                is_current=True,
                erp_id="ERP_SES_2627",
            )
            session.add(session_row)
            await session.flush()
            logger.info("seed.dummy.academic_session", erp_id=session_row.erp_id)
        else:
            logger.info("seed.dummy.academic_session_exists", erp_id="ERP_SES_2627")

        cls = (
            await session.execute(Class.__table__.select().where(Class.erp_id == "ERP_CLASS_10"))
        ).first()
        if cls is None:
            cls = Class(school_id=school.id, name="Class 10", erp_id="ERP_CLASS_10")
            session.add(cls)
            await session.flush()
            logger.info("seed.dummy.class", erp_id=cls.erp_id)
        else:
            logger.info("seed.dummy.class_exists", erp_id="ERP_CLASS_10")

        subject = (
            await session.execute(Subject.__table__.select().where(Subject.erp_id == "ERP_SUB_MATH"))
        ).first()
        if subject is None:
            subject = Subject(
                board_id=board.id,
                class_id=cls.id,
                name="Mathematics",
                erp_id="ERP_SUB_MATH",
            )
            session.add(subject)
            await session.flush()
            logger.info("seed.dummy.subject", erp_id=subject.erp_id)
        else:
            logger.info("seed.dummy.subject_exists", erp_id="ERP_SUB_MATH")

        chapter = (
            await session.execute(Chapter.__table__.select().where(Chapter.erp_id == "ERP_CHAP_ALG"))
        ).first()
        if chapter is None:
            chapter = Chapter(
                subject_id=subject.id,
                name="Algebra",
                sequence=1,
                erp_id="ERP_CHAP_ALG",
            )
            session.add(chapter)
            await session.flush()
            logger.info("seed.dummy.chapter", erp_id=chapter.erp_id)
        else:
            logger.info("seed.dummy.chapter_exists", erp_id="ERP_CHAP_ALG")

        unit = (
            await session.execute(Unit.__table__.select().where(Unit.erp_id == "ERP_UNIT_QUAD"))
        ).first()
        if unit is None:
            unit = Unit(
                chapter_id=chapter.id,
                name="Quadratic Equations",
                erp_id="ERP_UNIT_QUAD",
            )
            session.add(unit)
            await session.flush()
            logger.info("seed.dummy.unit", erp_id=unit.erp_id)
        else:
            logger.info("seed.dummy.unit_exists", erp_id="ERP_UNIT_QUAD")

        topic = (
            await session.execute(Topic.__table__.select().where(Topic.erp_id == "ERP_TOPIC_QF"))
        ).first()
        if topic is None:
            topic = Topic(
                unit_id=unit.id,
                name="Quadratic Formula",
                erp_id="ERP_TOPIC_QF",
            )
            session.add(topic)
            await session.flush()
            logger.info("seed.dummy.topic", erp_id=topic.erp_id)
        else:
            logger.info("seed.dummy.topic_exists", erp_id="ERP_TOPIC_QF")

        # ---- Accounts ------------------------------------------------------
        role_objs: dict[str, Role] = {}
        for role in ("SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT"):
            row = (
                await session.execute(Role.__table__.select().where(Role.name == role))
            ).first()
            if row is None:
                raise RuntimeError(f"Role {role} missing - run seed_roles_permissions first")
            role_objs[role] = await session.get(Role, row.id)

        users = [
            ("superadmin@ns-exam.com", "SUPER_ADMIN", "SUPER_ADMIN", None, None),
            ("admin@ns-exam.com", "ADMIN", "ADMIN", None, None),
            ("schooladmin@ns-exam.com", "SCHOOL_ADMIN", "SCHOOL_ADMIN", school.id, board.id),
            ("teacher@ns-exam.com", "TEACHER", "TEACHER", school.id, board.id),
            ("student@ns-exam.com", "EXTERNAL_STUDENT", "STUDENT", school.id, board.id),
        ]
        for email, user_type, role_name, school_id, board_id in users:
            existing = (
                await session.execute(User.__table__.select().where(User.email == email))
            ).first()
            if existing:
                logger.info("seed.dummy.user_exists", email=email)
                continue
            user = User(
                email=email,
                password_hash=hash_password(PASSWORD),
                user_type=user_type,
                auth_source="LOCAL",
                status="ACTIVE",
                school_id=school_id,
                board_id=board_id,
            )
            session.add(user)
            await session.flush()
            session.add(UserRole(user_id=user.id, role_id=role_objs[role_name].id))
            logger.info("seed.dummy.user_created", email=email, role=role_name)

            # Create the profile row to match the account.
            if user_type == "EXTERNAL_STUDENT":
                session.add(
                    StudentProfile(
                        student_type="EXTERNAL",
                        user_id=user.id,
                        name="Dummy Student",
                        roll_number="10A-001",
                        school_id=school_id,
                        board_id=board_id,
                        class_id=cls.id,
                        academic_session_id=session_row.id,
                        status="ACTIVE",
                    )
                )
            elif user_type == "TEACHER":
                teacher = TeacherProfile(
                    user_id=user.id,
                    erp_teacher_id="EMP_GVH_001",
                    name="Dummy Teacher",
                    school_id=school_id,
                    erp_id="ERP_TEACH_GVH_001",
                )
                session.add(teacher)
                await session.flush()
                session.add(TeacherSubjectMap(teacher_id=teacher.id, subject_id=subject.id))

        await session.flush()
        logger.info("seed.dummy.completed")


if __name__ == "__main__":
    asyncio.run(seed())
