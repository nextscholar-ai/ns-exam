"""
Phase 12 — Exam Management unit tests.

Tests:
  1. State Machine enforcement: legal transitions succeed, illegal ones raise BusinessRuleError.
  2. Regular Exam flow: full lifecycle (DRAFT → CONFIGURED → PAPER_GENERATED → APPROVED → PUBLISHED → ACTIVE → SUBMITTED).
  3. Regular Exam attempt limit: second attempt raises 409 Conflict.
  4. Mock Exam flow: multi-attempt generates new paper per attempt and toggles is_latest.
  5. Guest Join: lazy assignment generates join_code and creates guest student assignment.
"""
import uuid
import pytest

from app.core.exceptions import BusinessRuleError, ConflictError
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Class, School, Subject
from app.modules.blueprint.schemas import (
    BlueprintCreate,
    BlueprintSectionCreate,
    SectionDifficultyDistribution,
)
from app.modules.blueprint.service import BlueprintService
from app.modules.exam_management.domain.state_machine import validate_transition
from app.modules.exam_management.schemas import ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.student.models import StudentProfile


def _teacher(board_id: int = 1) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-exam-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=10,
        board_id=board_id,
        jti="jti-exam",
    )


# ---------------------------------------------------------------------------
# 1. State Machine Unit Tests (Pure Domain)
# ---------------------------------------------------------------------------

def test_state_machine_legal_transitions():
    """Legal state machine transitions must pass without exception."""
    validate_transition("DRAFT", "CONFIGURED")
    validate_transition("CONFIGURED", "PAPER_GENERATED")
    validate_transition("PAPER_GENERATED", "TEACHER_REVIEWING")
    validate_transition("TEACHER_REVIEWING", "APPROVED")
    validate_transition("APPROVED", "PUBLISHED")
    validate_transition("PUBLISHED", "SCHEDULED")
    validate_transition("SCHEDULED", "ACTIVE")
    validate_transition("ACTIVE", "COMPLETED")
    validate_transition("COMPLETED", "EVALUATING")
    validate_transition("EVALUATING", "RESULT_PUBLISHED")
    validate_transition("RESULT_PUBLISHED", "ARCHIVED")


def test_state_machine_illegal_transitions_raise():
    """Illegal state machine jumps must raise BusinessRuleError."""
    with pytest.raises(BusinessRuleError):
        validate_transition("DRAFT", "PUBLISHED")

    with pytest.raises(BusinessRuleError):
        validate_transition("CONFIGURED", "ACTIVE")

    with pytest.raises(BusinessRuleError):
        validate_transition("ACTIVE", "RESULT_PUBLISHED")


# ---------------------------------------------------------------------------
# 2. Integration / DB Tests (Exam & Attempt Lifecycle)
# ---------------------------------------------------------------------------

async def _seed_exam_environment(session):
    """Seed academic hierarchy, student, and an active blueprint."""
    from app.core.db.base_repository import BaseRepository
    from app.modules.identity.models import User

    board = await BaseRepository(session, Board).create(
        {"erp_id": "board-em-1", "name": "CBSE"}
    )
    school = await BaseRepository(session, School).create(
        {"erp_id": "school-em-1", "name": "School EM", "board_id": board.id}
    )
    cls = await BaseRepository(session, Class).create(
        {"erp_id": "class-em-1", "name": "Class 10", "school_id": school.id}
    )
    subj = await BaseRepository(session, Subject).create(
        {"erp_id": "subj-em-1", "name": "Science", "board_id": board.id, "class_id": cls.id}
    )

    user = await BaseRepository(session, User).create(
        {
            "email": "student1@test.com",
            "user_type": "ERP_STUDENT",
            "auth_source": "ERP",
            "status": "ACTIVE",
            "school_id": school.id,
        }
    )
    student = await BaseRepository(session, StudentProfile).create(
        {
            "erp_student_id": "std-em-1",
            "school_id": school.id,
            "user_id": user.id,
            "name": "Rahul Sharma",
            "student_type": "ERP",
        }
    )

    bp_service = BlueprintService(session)
    bp_create = BlueprintCreate(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subj.id,
        name="CBSE 10 Science Blueprint",
        total_marks=50.0,
        duration_minutes=60,
        sections=[
            BlueprintSectionCreate(
                section_label="A",
                question_type="OBJECTIVE",
                section_marks=50.0,
                question_count=5,
                difficulty_distribution=SectionDifficultyDistribution(
                    EASY=20, MEDIUM=60, HARD=20
                ),
            )
        ],
    )
    bp_dict = await bp_service.create_blueprint(bp_create, current_user=_teacher(board.id))
    bp_pub_id = uuid.UUID(bp_dict["public_id"])
    await bp_service.change_blueprint_status(bp_pub_id, "ACTIVE")

    # Create exam configuration
    from app.modules.blueprint.schemas import ExamConfigCreate
    ec_dict = await bp_service.create_exam_config(
        ExamConfigCreate(
            blueprint_id=(await bp_service._bp_repo.get_by(public_id=str(bp_pub_id))).id,
            exam_name="Term 1 Final Exam",
            academic_session_id=1,
            exam_type="REGULAR",
        )
    )

    await session.flush()
    return board, school, cls, subj, student, ec_dict


@pytest.mark.asyncio
async def test_regular_exam_full_lifecycle(sqlite_session):
    """Test full Regular exam lifecycle: create → configure → generate → approve → publish → start attempt → submit."""
    board, school, cls, subj, student, ec_dict = await _seed_academic_hierarchy_and_ec(sqlite_session)
    exam_service = ExamService(sqlite_session)
    attempt_service = AttemptService(sqlite_session)
    teacher = _teacher(board.id)

    # 1. Create Exam (DRAFT)
    ex = await exam_service.create_exam(
        ExamCreate(
            board_id=board.id,
            school_id=school.id,
            class_id=cls.id,
            subject_id=subj.id,
            title="Class 10 Science Final",
            exam_type="REGULAR",
        ),
        current_user=teacher,
    )
    assert ex["status"] == "DRAFT"
    ex_pub_id = uuid.UUID(ex["public_id"])

    # 2. Configure Exam (DRAFT → CONFIGURED)
    from app.modules.exam_management.schemas import ExamConfigure
    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id
    configured = await exam_service.configure_exam(
        ex_pub_id, ExamConfigure(exam_configuration_id=ec_id), current_user=teacher
    )
    assert configured["status"] == "CONFIGURED"

    # 3. Generate Papers (CONFIGURED → PAPER_GENERATED)
    generated = await exam_service.generate_papers_for_exam(ex_pub_id, current_user=teacher)
    assert generated["status"] == "PAPER_GENERATED"

    # 4. Approve Exam (PAPER_GENERATED → APPROVED)
    approved = await exam_service.approve_exam(ex_pub_id, current_user=teacher)
    assert approved["status"] == "APPROVED"

    # 5. Publish Exam (APPROVED → PUBLISHED)
    published = await exam_service.publish_exam(ex_pub_id, current_user=teacher)
    assert published["status"] == "PUBLISHED"
    assert published["join_code"] is not None

    # 6. Start Student Attempt
    att = await attempt_service.start_attempt(ex_pub_id, student.id, current_user=teacher)
    assert att["status"] == "IN_PROGRESS"
    assert att["attempt_number"] == 1
    assert att["is_latest"] is True

    # 7. Submit Attempt
    att_pub_id = uuid.UUID(att["public_id"])
    submitted = await attempt_service.submit_attempt(att_pub_id, current_user=teacher)
    assert submitted["status"] == "SUBMITTED"

    # 8. Second attempt on Regular exam must raise 409 Conflict
    with pytest.raises(ConflictError):
        await attempt_service.start_attempt(ex_pub_id, student.id, current_user=teacher)


@pytest.mark.asyncio
async def test_mock_exam_multi_attempt_flow(sqlite_session):
    """Test Mock exam multi-attempt flow: attempt 1 & attempt 2 both succeed, is_latest toggles correctly."""
    board, school, cls, subj, student, ec_dict = await _seed_academic_hierarchy_and_ec(sqlite_session)
    exam_service = ExamService(sqlite_session)
    attempt_service = AttemptService(sqlite_session)
    teacher = _teacher(board.id)

    # Create & configure Mock Exam
    ex = await exam_service.create_exam(
        ExamCreate(
            board_id=board.id,
            school_id=school.id,
            class_id=cls.id,
            subject_id=subj.id,
            title="Science Mock Practice",
            exam_type="MOCK",
        ),
        current_user=teacher,
    )
    ex_pub_id = uuid.UUID(ex["public_id"])
    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id

    from app.modules.exam_management.schemas import ExamConfigure
    await exam_service.configure_exam(ex_pub_id, ExamConfigure(exam_configuration_id=ec_id))
    await exam_service.generate_papers_for_exam(ex_pub_id)
    await exam_service.approve_exam(ex_pub_id)
    await exam_service.publish_exam(ex_pub_id)

    # Attempt 1
    att1 = await attempt_service.start_attempt(ex_pub_id, student.id)
    assert att1["attempt_number"] == 1
    assert att1["is_latest"] is True

    # Submit Attempt 1
    await attempt_service.submit_attempt(uuid.UUID(att1["public_id"]))

    # Attempt 2 (Mock allows repeat attempts)
    att2 = await attempt_service.start_attempt(ex_pub_id, student.id)
    assert att2["attempt_number"] == 2
    assert att2["is_latest"] is True

    # Check attempt history
    attempts = await attempt_service.attempt_repo.list_attempts_for_student(
        (await exam_service.exam_repo.get_by(public_id=str(ex_pub_id))).id,
        student.id,
    )
    assert len(attempts) == 2
    assert attempts[0].is_latest is False
    assert attempts[1].is_latest is True


@pytest.mark.asyncio
async def test_guest_join_flow(sqlite_session):
    """Guest student can join exam using join code."""
    board, school, cls, subj, student, ec_dict = await _seed_academic_hierarchy_and_ec(sqlite_session)
    exam_service = ExamService(sqlite_session)

    ex = await exam_service.create_exam(
        ExamCreate(
            board_id=board.id,
            school_id=school.id,
            class_id=cls.id,
            subject_id=subj.id,
            title="Public Quiz Exam",
            exam_type="REGULAR",
        )
    )
    ex_pub_id = uuid.UUID(ex["public_id"])
    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id

    from app.modules.exam_management.schemas import ExamConfigure
    await exam_service.configure_exam(ex_pub_id, ExamConfigure(exam_configuration_id=ec_id))
    await exam_service.generate_papers_for_exam(ex_pub_id)
    await exam_service.approve_exam(ex_pub_id)
    pub = await exam_service.publish_exam(ex_pub_id)

    join_code = pub["join_code"]
    guest_res = await exam_service.join_guest(join_code, "Aarav Patel")

    assert guest_res["exam_public_id"] == str(ex_pub_id)
    assert guest_res["join_code"] == join_code
    assert guest_res["student_id"] is not None


async def _seed_academic_hierarchy_and_ec(session):
    """Helper wrapper for test fixtures."""
    return await _seed_exam_environment(session)
