"""
Phase 16 — Analytics & Reporting Engine unit tests.

Tests:
  1. Pure domain calculators: compute_trend_direction, evaluate_student_risk, compute_pass_percentage.
  2. Report snapshot state machine: legal transitions pass, illegal raise BusinessRuleError.
  3. AnalyticsService integration: get_student_dashboard (computes avg score, risk, trends, stores summary).
  4. AnalyticsService integration: get_class_analytics (class avg, highest/lowest, pass rate).
  5. ReportService integration: generate student report card & exam analysis snapshots, publish report.
"""
from __future__ import annotations

import uuid
import pytest

from app.core.exceptions import BusinessRuleError
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.analytics.domain.calculators import (
    compute_pass_percentage,
    compute_trend_direction,
    evaluate_student_risk,
)
from app.modules.analytics.service import AnalyticsService
from app.modules.blueprint.schemas import (
    BlueprintCreate,
    BlueprintSectionCreate,
    ExamConfigCreate,
    SectionDifficultyDistribution,
)
from app.modules.blueprint.service import BlueprintService
from app.modules.evaluation.service import EvaluationService, OMRService
from app.modules.exam_management.schemas import ExamConfigure, ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.learning_profile.service import MasteryService
from app.modules.question_bank.schemas import ObjectiveQuestionCreate, OptionSchema
from app.modules.question_bank.service import QuestionBankService
from app.modules.reports.domain.state_machine import validate_report_transition
from app.modules.reports.service import ReportService
from app.modules.student.models import StudentProfile
from app.core.db.base_repository import BaseRepository


# ---------------------------------------------------------------------------
# 1. Pure Domain Calculator Tests
# ---------------------------------------------------------------------------

def test_compute_trend_direction_improving():
    """Scores increasing by > 0.05 yield IMPROVING trend."""
    scores = [0.2, 0.3, 0.7, 0.8]
    assert compute_trend_direction(scores) == "IMPROVING"


def test_compute_trend_direction_declining():
    """Scores decreasing by > 0.05 yield DECLINING trend."""
    scores = [0.8, 0.7, 0.3, 0.2]
    assert compute_trend_direction(scores) == "DECLINING"


def test_compute_trend_direction_stable():
    """Flattish scores yield STABLE trend."""
    scores = [0.5, 0.5, 0.5, 0.5]
    assert compute_trend_direction(scores) == "STABLE"


def test_evaluate_student_risk_at_risk():
    """Student with low mastery (<0.40) or failed exams is flagged as at risk."""
    is_risk, reasons = evaluate_student_risk(overall_mastery=0.35, failed_exams_count=1, trend_direction="STABLE")
    assert is_risk is True
    assert len(reasons) >= 1

    is_risk2, reasons2 = evaluate_student_risk(overall_mastery=0.60, failed_exams_count=2, trend_direction="STABLE")
    assert is_risk2 is True
    assert "Failed 2 exams" in reasons2[0]


def test_evaluate_student_risk_not_at_risk():
    """High mastery student with 0 failed exams is not at risk."""
    is_risk, reasons = evaluate_student_risk(overall_mastery=0.85, failed_exams_count=0, trend_direction="IMPROVING")
    assert is_risk is False
    assert len(reasons) == 0


def test_compute_pass_percentage():
    """Calculates pass rate percentage accurately."""
    assert compute_pass_percentage(8, 10) == 80.0
    assert compute_pass_percentage(0, 5) == 0.0
    assert compute_pass_percentage(0, 0) == 0.0


# ---------------------------------------------------------------------------
# 2. Report State Machine Unit Tests
# ---------------------------------------------------------------------------

def test_report_state_machine_legal_transitions():
    """Legal report snapshot state transitions must pass."""
    validate_report_transition("GENERATED", "PUBLISHED")
    validate_report_transition("GENERATED", "ARCHIVED")
    validate_report_transition("PUBLISHED", "ARCHIVED")


def test_report_state_machine_illegal_transitions_raise():
    """Illegal state jumps must raise BusinessRuleError."""
    with pytest.raises(BusinessRuleError):
        validate_report_transition("ARCHIVED", "PUBLISHED")

    with pytest.raises(BusinessRuleError):
        validate_report_transition("PUBLISHED", "GENERATED")


# ---------------------------------------------------------------------------
# 3. Integration — Analytics & Report Services Test
# ---------------------------------------------------------------------------

async def _seed_analytics_environment(session):
    """Seed full environment: academic, student, exam, evaluation locked -> Phase 14 mastery created."""
    board = await BaseRepository(session, Board).create({"erp_id": "board-an-1", "name": "CBSE"})
    school = await BaseRepository(session, School).create({"erp_id": "school-an-1", "name": "School AN", "board_id": board.id})
    cls = await BaseRepository(session, Class).create({"erp_id": "class-an-1", "name": "Class 10", "school_id": school.id})
    subj = await BaseRepository(session, Subject).create({"erp_id": "subj-an-1", "name": "Maths", "board_id": board.id, "class_id": cls.id})
    chap = await BaseRepository(session, Chapter).create({"erp_id": "chap-an-1", "subject_id": subj.id, "name": "Algebra", "sequence": 1})
    unit_obj = await BaseRepository(session, Topic).create({"erp_id": "top-an-1", "unit_id": chap.id, "name": "Linear Equations"})

    qb = QuestionBankService(session)
    teacher = CurrentUser(public_id="t-an", user_type="TEACHER", auth_source="ERP", roles=["TEACHER"], school_id=10, board_id=board.id, jti="jti")

    obj_q = await qb.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            primary_chapter_id=chap.id, primary_topic_id=unit_obj.id,
            question_text="2x = 4, x = ?",
            options=[OptionSchema(label="A", text="2"), OptionSchema(label="B", text="4")],
            correct_option="A", marks=2.0, difficulty="EASY",
        ),
        current_user=teacher,
    )
    await qb.change_status(obj_q["public_id"], "ACTIVE", current_user=teacher)

    user = await BaseRepository(session, User).create(
        {"email": "student_an@test.com", "user_type": "ERP_STUDENT", "auth_source": "ERP", "status": "ACTIVE", "school_id": school.id}
    )
    student = await BaseRepository(session, StudentProfile).create(
        {"erp_student_id": "std-an-1", "school_id": school.id, "user_id": user.id, "name": "Karan Verma", "student_type": "ERP"}
    )

    bp_service = BlueprintService(session)
    bp_dict = await bp_service.create_blueprint(
        BlueprintCreate(
            board_id=board.id, class_id=cls.id, subject_id=subj.id,
            name="Maths Blueprint", total_marks=2.0, duration_minutes=30,
            sections=[
                BlueprintSectionCreate(section_label="A", question_type="OBJECTIVE", section_marks=2.0, question_count=1, difficulty_distribution=SectionDifficultyDistribution(EASY=100, MEDIUM=0, HARD=0)),
            ],
        ),
        current_user=teacher,
    )
    bp_pub_id = uuid.UUID(bp_dict["public_id"])
    await bp_service.change_blueprint_status(bp_pub_id, "ACTIVE")

    ec_dict = await bp_service.create_exam_config(
        ExamConfigCreate(
            blueprint_id=(await bp_service._bp_repo.get_by(public_id=str(bp_pub_id))).id,
            exam_name="Maths Quiz", academic_session_id=1, exam_type="REGULAR",
        )
    )

    exam_service = ExamService(session)
    attempt_service = AttemptService(session)
    ex = await exam_service.create_exam(
        ExamCreate(board_id=board.id, school_id=school.id, class_id=cls.id, subject_id=subj.id, title="Maths Midterm", exam_type="REGULAR"),
        current_user=teacher,
    )
    ex_pub_id = uuid.UUID(ex["public_id"])

    ec_id = (await exam_service.ec_repo.get_by(public_id=ec_dict["public_id"])).id
    await exam_service.configure_exam(ex_pub_id, ExamConfigure(exam_configuration_id=ec_id))
    await exam_service.generate_papers_for_exam(ex_pub_id)
    await exam_service.approve_exam(ex_pub_id)
    await exam_service.publish_exam(ex_pub_id)

    att = await attempt_service.start_attempt(ex_pub_id, student.id, current_user=teacher)
    await attempt_service.submit_attempt(uuid.UUID(att["public_id"]), current_user=teacher)

    omr_service = OMRService(session)
    eval_service = EvaluationService(session)
    mastery_service = MasteryService(session)

    # Correct answer -> evaluation completed, locked & mastery updated
    await omr_service.process_omr_upload(attempt_id=att["id"], raw_bubble_matrix={"1": {"A": 0.98, "B": 0.01}})
    eval_obj = await eval_service.eval_repo.get_by_attempt(att["id"])
    await eval_service.complete_evaluation(eval_obj.public_id)
    await eval_service.lock_evaluation(eval_obj.public_id, current_user=teacher)
    await mastery_service.process_evaluation(eval_obj.public_id)

    return board, cls, subj, chap, unit_obj, student, ex, att


@pytest.mark.asyncio
async def test_analytics_service_student_dashboard(sqlite_session):
    """
    Integration test: AnalyticsService computes student performance dashboard,
    storing cached StudentAnalyticsSummary row.
    """
    board, cls, subj, chap, unit_obj, student, ex, att = await _seed_analytics_environment(sqlite_session)

    analytics_service = AnalyticsService(sqlite_session)

    dash = await analytics_service.get_student_dashboard(student.id, subject_id=subj.id)

    assert dash["student_id"] == student.id
    assert dash["subject_id"] == subj.id
    assert dash["total_exams_taken"] == 1
    assert dash["passed_exams_count"] == 1
    assert dash["failed_exams_count"] == 0
    assert dash["average_percentage"] == 100.0
    assert dash["overall_mastery"] > 0.0
    assert dash["is_at_risk"] is False


@pytest.mark.asyncio
async def test_analytics_service_class_analytics(sqlite_session):
    """
    Integration test: AnalyticsService computes class-level exam performance analytics.
    """
    board, cls, subj, chap, unit_obj, student, ex, att = await _seed_analytics_environment(sqlite_session)

    analytics_service = AnalyticsService(sqlite_session)

    class_analytics = await analytics_service.get_class_analytics(
        class_id=cls.id, exam_id=ex["id"], subject_id=subj.id
    )

    assert class_analytics["class_id"] == cls.id
    assert class_analytics["appeared_students_count"] == 1
    assert class_analytics["passed_students_count"] == 1
    assert class_analytics["pass_percentage"] == 100.0
    assert class_analytics["class_average_score"] == 2.0


@pytest.mark.asyncio
async def test_report_service_student_report_card_lifecycle(sqlite_session):
    """
    Integration test: ReportService generates student progress report card snapshot
    and publishes it (GENERATED -> PUBLISHED).
    """
    board, cls, subj, chap, unit_obj, student, ex, att = await _seed_analytics_environment(sqlite_session)

    report_service = ReportService(sqlite_session)

    # 1. Generate student report card
    report = await report_service.generate_student_report_card(
        student_id=student.id,
        subject_id=subj.id,
        title="Term 1 Algebra Report Card",
    )

    assert report["report_type"] == "STUDENT_PROGRESS"
    assert report["status"] == "GENERATED"
    assert report["student_id"] == student.id
    assert "Algebra" in report["summary_text"] or "Progress Report" in report["summary_text"]

    # 2. Publish report
    published = await report_service.publish_report(report["public_id"])
    assert published["status"] == "PUBLISHED"
    assert published["published_at"] is not None


@pytest.mark.asyncio
async def test_report_service_exam_analysis_report(sqlite_session):
    """
    Integration test: ReportService generates exam analysis report snapshot.
    """
    board, cls, subj, chap, unit_obj, student, ex, att = await _seed_analytics_environment(sqlite_session)

    report_service = ReportService(sqlite_session)

    exam_report = await report_service.generate_exam_analysis_report(
        exam_id=ex["id"],
        class_id=cls.id,
        subject_id=subj.id,
    )

    assert exam_report["report_type"] == "EXAM_ANALYSIS"
    assert exam_report["status"] == "GENERATED"
    assert exam_report["exam_id"] == ex["id"]
    assert exam_report["class_id"] == cls.id
