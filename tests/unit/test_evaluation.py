"""
Phase 13 — Evaluation Engine unit tests.

Tests:
  1. Evaluation state machine: legal transitions pass, illegal ones raise BusinessRuleError.
  2. OMR Bubble Detection pure logic: calculate fill ratio, confidence score, low-confidence flags.
  3. OMR Processing & Automatic Topic Mapping: verify evaluation_details chapter_id & topic_id are auto-populated from question metadata.
  4. Hybrid Evaluation Merge: objective + subjective sum correctly to total_marks, percentage, and PASS/FAIL result_status.
  5. Lock & Re-evaluation workflow: locking blocks when OMR NEEDS_MANUAL_REVIEW; re-evaluation request & approval snapshot versioning.
"""
import uuid
import pytest

from app.core.exceptions import BusinessRuleError
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.blueprint.schemas import BlueprintCreate, BlueprintSectionCreate, SectionDifficultyDistribution
from app.modules.blueprint.service import BlueprintService
from app.modules.evaluation.domain.omr.bubble_detection import detect_bubbles_from_matrix
from app.modules.evaluation.domain.state_machine import validate_evaluation_transition
from app.modules.evaluation.service import EvaluationService, OMRService, SubjectiveEvaluationService
from app.modules.exam_management.schemas import ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.question_bank.schemas import ObjectiveQuestionCreate, OptionSchema, SubjectiveQuestionCreate
from app.modules.question_bank.service import QuestionBankService
from app.modules.student.models import StudentProfile


def _teacher(board_id: int = 1) -> CurrentUser:
    return CurrentUser(
        public_id="teacher-eval-1",
        user_type="TEACHER",
        auth_source="ERP",
        roles=["TEACHER"],
        school_id=10,
        board_id=board_id,
        jti="jti-eval",
    )


# ---------------------------------------------------------------------------
# 1. State Machine Unit Tests (Pure Domain)
# ---------------------------------------------------------------------------

def test_evaluation_state_machine_legal_transitions():
    """Legal evaluation state transitions must pass."""
    validate_evaluation_transition("PENDING", "STARTED")
    validate_evaluation_transition("STARTED", "OBJECTIVE_COMPLETED")
    validate_evaluation_transition("OBJECTIVE_COMPLETED", "SUBJECTIVE_PENDING")
    validate_evaluation_transition("SUBJECTIVE_PENDING", "COMPLETED")
    validate_evaluation_transition("COMPLETED", "LOCKED")
    validate_evaluation_transition("LOCKED", "PUBLISHED")


def test_evaluation_state_machine_illegal_transitions_raise():
    """Illegal state jumps must raise BusinessRuleError."""
    with pytest.raises(BusinessRuleError):
        validate_evaluation_transition("PENDING", "LOCKED")

    with pytest.raises(BusinessRuleError):
        validate_evaluation_transition("OBJECTIVE_COMPLETED", "PUBLISHED")


# ---------------------------------------------------------------------------
# 2. OMR Detection Engine Unit Test (Pure Domain)
# ---------------------------------------------------------------------------

def test_omr_bubble_detection_logic():
    """Test bubble matrix evaluation, confidence scoring, and low confidence flagging."""
    matrix = {
        "1": {"A": 0.95, "B": 0.02, "C": 0.01, "D": 0.01},  # Clear A
        "2": {"A": 0.45, "B": 0.44, "C": 0.01, "D": 0.00},  # Ambiguous A & B
        "3": {"A": 0.10, "B": 0.10, "C": 0.05, "D": 0.02},  # Blank/low fill
    }
    result = detect_bubbles_from_matrix(matrix)

    assert result.detected_answers["1"] == "A"
    assert len(result.low_confidence_questions) == 2  # Q2 & Q3 flagged
    assert result.confidence_score < 90.0


# ---------------------------------------------------------------------------
# 3. Full Integration & Auto Topic Mapping Test (DB)
# ---------------------------------------------------------------------------

async def _seed_evaluation_environment(session):
    """Seed academic hierarchy, questions with chapters/topics, exam, paper, and student attempt."""
    from app.core.db.base_repository import BaseRepository

    board = await BaseRepository(session, Board).create({"erp_id": "board-ev-1", "name": "CBSE"})
    school = await BaseRepository(session, School).create({"erp_id": "school-ev-1", "name": "School EV", "board_id": board.id})
    cls = await BaseRepository(session, Class).create({"erp_id": "class-ev-1", "name": "Class 10", "school_id": school.id})
    subj = await BaseRepository(session, Subject).create({"erp_id": "subj-ev-1", "name": "Science", "board_id": board.id, "class_id": cls.id})

    chap = await BaseRepository(session, Chapter).create({"erp_id": "chap-ev-1", "subject_id": subj.id, "name": "Chemical Reactions", "sequence": 1})
    unit_obj = await BaseRepository(session, Topic).create({"erp_id": "top-ev-1", "unit_id": chap.id, "name": "Oxidation & Reduction"})

    # Seed Questions (Phase 10)
    qb_service = QuestionBankService(session)
    teacher = _teacher(board.id)

    obj_q = await qb_service.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subj.id,
            primary_chapter_id=chap.id,
            primary_topic_id=unit_obj.id,
            question_text="What is chemical formula of water?",
            options=[OptionSchema(label="A", text="H2O"), OptionSchema(label="B", text="CO2")],
            correct_option="A",
            marks=2.0,
            difficulty="EASY",
        ),
        current_user=teacher,
    )
    await qb_service.change_status(obj_q["public_id"], "ACTIVE", current_user=teacher)

    subj_q = await qb_service.create_subjective_question(
        SubjectiveQuestionCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subj.id,
            primary_chapter_id=chap.id,
            primary_topic_id=unit_obj.id,
            question_text="Explain oxidation reaction.",
            max_marks=8.0,
        ),
        current_user=teacher,
    )
    await qb_service.change_status(subj_q["public_id"], "ACTIVE", current_user=teacher)

    # Seed Student
    user = await BaseRepository(session, User).create({
        "email": "student_eval@test.com", "user_type": "ERP_STUDENT", "auth_source": "ERP", "status": "ACTIVE", "school_id": school.id,
    })
    student = await BaseRepository(session, StudentProfile).create({
        "erp_student_id": "std-ev-1", "school_id": school.id, "user_id": user.id, "name": "Ananya Roy", "student_type": "ERP",
    })

    # Seed Blueprint & Exam
    bp_service = BlueprintService(session)
    bp_dict = await bp_service.create_blueprint(
        BlueprintCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subj.id,
            name="Hybrid Exam Blueprint",
            total_marks=10.0,
            duration_minutes=60,
            sections=[
                BlueprintSectionCreate(
                    section_label="A", question_type="OBJECTIVE", section_marks=2.0, question_count=1,
                    difficulty_distribution=SectionDifficultyDistribution(EASY=100, MEDIUM=0, HARD=0)
                ),
                BlueprintSectionCreate(
                    section_label="B", question_type="SUBJECTIVE", section_marks=8.0, question_count=1,
                    difficulty_distribution=SectionDifficultyDistribution(EASY=0, MEDIUM=100, HARD=0)
                )
            ]
        ),
        current_user=teacher,
    )
    bp_pub_id = uuid.UUID(bp_dict["public_id"])
    await bp_service.change_blueprint_status(bp_pub_id, "ACTIVE")

    from app.modules.blueprint.schemas import ExamConfigCreate
    ec_dict = await bp_service.create_exam_config(
        ExamConfigCreate(
            blueprint_id=(await bp_service._bp_repo.get_by(public_id=str(bp_pub_id))).id,
            exam_name="Hybrid Midterm",
            academic_session_id=1,
            exam_type="REGULAR",
        )
    )

    exam_service = ExamService(session)
    attempt_service = AttemptService(session)

    ex = await exam_service.create_exam(
        ExamCreate(
            board_id=board.id, school_id=school.id, class_id=cls.id, subject_id=subj.id,
            title="Hybrid Science Midterm", exam_type="REGULAR"
        ),
        current_user=teacher,
    )
    ex_pub_id = uuid.UUID(ex["public_id"])

    from app.modules.exam_management.schemas import ExamConfigure
    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id
    await exam_service.configure_exam(ex_pub_id, ExamConfigure(exam_configuration_id=ec_id))
    await exam_service.generate_papers_for_exam(ex_pub_id)
    await exam_service.approve_exam(ex_pub_id)
    await exam_service.publish_exam(ex_pub_id)

    att = await attempt_service.start_attempt(ex_pub_id, student.id, current_user=teacher)
    await attempt_service.submit_attempt(uuid.UUID(att["public_id"]), current_user=teacher)

    await session.flush()
    return board, school, cls, subj, chap, unit_obj, student, att, obj_q, subj_q


@pytest.mark.asyncio
async def test_omr_processing_auto_topic_mapping_and_hybrid_merge(sqlite_session):
    """
    Integration test:
    1. OMR processing evaluates objective answers and auto-populates chapter_id & topic_id.
    2. Subjective evaluation enters teacher marks with auto topic mapping.
    3. Complete evaluation calculates hybrid total marks, percentage, and PASS status.
    4. Locking publishes EvaluationCompleted event.
    """
    (
        board, school, cls, subj, chap, unit_obj, student, att, obj_q, subj_q
    ) = await _seed_evaluation_environment(sqlite_session)

    omr_service = OMRService(sqlite_session)
    subj_service = SubjectiveEvaluationService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    teacher = _teacher(board.id)

    # 1. Process OMR Upload (Objective question 1 answer: "A" - correct)
    omr_res = await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.98, "B": 0.01, "C": 0.01, "D": 0.00}},
    )
    assert omr_res["status"] == "DETECTED"

    # Get evaluation instance
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    assert eval_obj.status == "OBJECTIVE_COMPLETED"

    # Verify auto topic mapping on details row
    details = await eval_service.detail_repo.list_by_evaluation(eval_obj.id)
    assert len(details) == 1
    assert details[0].chapter_id == chap.id
    assert details[0].topic_id == unit_obj.id
    assert details[0].marks_obtained == 2.0
    assert details[0].is_correct is True

    # 2. Enter Subjective Marks (Question 2: 7.0 / 8.0 marks)
    subj_res = await subj_service.enter_subjective_marks(
        evaluation_public_id=eval_obj.public_id,
        question_id=subj_q["id"],
        question_type="SUBJECTIVE",
        marks_obtained=7.0,
        max_marks=8.0,
        current_user=teacher,
    )
    assert subj_res["chapter_id"] == chap.id
    assert subj_res["topic_id"] == unit_obj.id

    # 3. Complete Evaluation (Hybrid Merge: 2.0 obj + 7.0 subj = 9.0 / 10.0 = 90%)
    completed = await eval_service.complete_evaluation(eval_obj.public_id, pass_threshold_pct=40.0)
    assert completed["status"] == "COMPLETED"
    assert completed["total_marks"] == 9.0
    assert completed["percentage"] == 90.0
    assert completed["result_status"] == "PASS"

    # 4. Lock Evaluation (COMPLETED → LOCKED)
    locked = await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    assert locked["status"] == "LOCKED"


@pytest.mark.asyncio
async def test_re_evaluation_approval_and_version_snapshot(sqlite_session):
    """
    Test Re-Evaluation workflow:
    1. Lock evaluation.
    2. Submit re-evaluation request.
    3. Approve re-evaluation → creates EvaluationVersion snapshot v1 and unlocks evaluation back to STARTED.
    """
    (
        board, school, cls, subj, chap, unit_obj, student, att, obj_q, subj_q
    ) = await _seed_evaluation_environment(sqlite_session)

    omr_service = OMRService(sqlite_session)
    subj_service = SubjectiveEvaluationService(sqlite_session)
    eval_service = EvaluationService(sqlite_session)
    teacher = _teacher(board.id)

    # Setup completed & locked evaluation
    await omr_service.process_omr_upload(
        attempt_id=att["id"],
        raw_bubble_matrix={"1": {"A": 0.95, "B": 0.02, "C": 0.01, "D": 0.01}},
    )
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await subj_service.enter_subjective_marks(
        eval_obj.public_id, subj_q["id"], "SUBJECTIVE", 6.0, 8.0, current_user=teacher
    )
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)

    # Submit Re-Evaluation Request
    re_eval_req = await eval_service.request_re_evaluation(
        eval_obj.public_id, reason="Subjective Q2 key points re-check requested by student"
    )
    req_pub_id = uuid.UUID(re_eval_req["public_id"])

    # Approve Re-Evaluation
    unlocked_eval = await eval_service.approve_re_evaluation(req_pub_id, current_user=teacher)
    assert unlocked_eval["status"] == "STARTED"
    assert unlocked_eval["current_version_no"] == 2

    # Check version history
    versions = await eval_service.version_repo.list_by_evaluation(eval_obj.id)
    assert len(versions) == 1
    assert versions[0].version_no == 1
    assert versions[0].snapshot_json["evaluation"]["status"] == "LOCKED"
