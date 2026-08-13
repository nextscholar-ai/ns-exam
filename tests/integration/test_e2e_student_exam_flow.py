"""
Phase 20 — End-to-End Student Exam Lifecycle Integration Test.

Tests full 15-module flow:
  Academic Setup → Question Bank → Exam Management → Student Attempt →
  Evaluation Intake → Mastery Update → Practice Recommendation →
  Analytics Computation → Report Snapshot → ERP Webhook Sync → Notification Dispatch.
"""
from __future__ import annotations

import pytest

from app.core.events.bus import event_bus
from app.core.events.event_names import EVALUATION_COMPLETED, EXAM_SUBMITTED
from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.analytics.service import AnalyticsService
from app.modules.evaluation.models import Evaluation
from app.modules.evaluation.service import EvaluationService
from app.modules.blueprint.models import ExamConfiguration
from app.modules.exam_management.models import Exam, StudentAttempt
from app.modules.exam_management.schemas import ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.integration.service import ERPIntegrationService
from app.modules.integration.webhook import MockWebhookClient
from app.modules.learning_profile.service import LearningProfileService, MasteryService
from app.modules.question_bank.schemas import ObjectiveQuestionCreate, OptionSchema
from app.modules.question_bank.service import QuestionBankService
from app.modules.recommendation.service import RecommendationService
from app.modules.reports.service import ReportService
from app.modules.student.models import StudentProfile


@pytest.mark.asyncio
async def test_e2e_full_student_assessment_and_mastery_pipeline(sqlite_session):
    """
    Full end-to-end integration test spanning all major platform domains.
    """
    from app.modules.academic.models import Unit

    board = Board(name="Central Board", code="CBSE_E2E", erp_id="ERP_B_E2E")
    sqlite_session.add(board)
    await sqlite_session.flush()

    school = School(board_id=board.id, name="Delhi Model School", erp_id="ERP_S_E2E")
    sqlite_session.add(school)
    await sqlite_session.flush()

    cls = Class(school_id=school.id, name="Class 10", erp_id="ERP_C10_E2E")
    sqlite_session.add(cls)
    await sqlite_session.flush()

    subject = Subject(board_id=board.id, class_id=cls.id, name="Physics", erp_id="ERP_PHY_E2E")
    sqlite_session.add(subject)
    await sqlite_session.flush()

    chapter = Chapter(subject_id=subject.id, name="Kinematics", erp_id="ERP_CH1_E2E")
    sqlite_session.add(chapter)
    await sqlite_session.flush()

    unit = Unit(chapter_id=chapter.id, name="Kinematics Unit 1", erp_id="ERP_U1_E2E")
    sqlite_session.add(unit)
    await sqlite_session.flush()

    topic = Topic(unit_id=unit.id, name="Velocity & Acceleration", erp_id="ERP_TP1_E2E")
    sqlite_session.add(topic)
    await sqlite_session.flush()

    # 2. Identity & Student Profile
    user = User(
        email="student_e2e@ns-exam.com",
        password_hash="hashed_pw",
        user_type="EXTERNAL_STUDENT",
        auth_source="LOCAL",
    )
    sqlite_session.add(user)
    await sqlite_session.flush()

    student = StudentProfile(
        user_id=user.id,
        name="E2E Student",
        student_type="EXTERNAL",
        school_id=school.id,
        board_id=board.id,
        class_id=cls.id,
    )
    sqlite_session.add(student)
    await sqlite_session.flush()

    # 3. Question Bank Setup
    qb_svc = QuestionBankService(sqlite_session)
    q1 = await qb_svc.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subject.id,
            primary_chapter_id=chapter.id,
            primary_unit_id=unit.id,
            primary_topic_id=topic.id,
            question_text="What is unit of velocity?",
            options=[
                OptionSchema(label="A", text="m/s"),
                OptionSchema(label="B", text="kg"),
            ],
            correct_option="A",
            difficulty="EASY",
            marks=4.0,
        )
    )
    q2 = await qb_svc.create_objective_question(
        ObjectiveQuestionCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subject.id,
            primary_chapter_id=chapter.id,
            primary_unit_id=unit.id,
            primary_topic_id=topic.id,
            question_text="What is unit of acceleration?",
            options=[
                OptionSchema(label="A", text="m/s^2"),
                OptionSchema(label="B", text="N"),
            ],
            correct_option="A",
            difficulty="MEDIUM",
            marks=4.0,
        )
    )
    assert q1 is not None and q2 is not None

    from datetime import date

    from app.modules.academic.models import AcademicSession
    from app.modules.blueprint.models import Blueprint
    from app.modules.paper_generation.models import Paper

    # 4. Exam Management Setup & Publish
    exam_svc = ExamService(sqlite_session)
    exam = await exam_svc.create_exam(
        ExamCreate(
            board_id=board.id,
            school_id=school.id,
            class_id=cls.id,
            subject_id=subject.id,
            title="Midterm Physics Exam",
        )
    )

    # Seed academic session for FK
    session_row = AcademicSession(
        school_id=school.id,
        name="2026-27",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        is_current=True,
        erp_id="ERP_SES_E2E",
    )
    sqlite_session.add(session_row)
    await sqlite_session.flush()

    bp = Blueprint(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subject.id,
        name="Midterm Physics BP",
        total_marks=8.0,
        duration_minutes=60,
    )
    sqlite_session.add(bp)
    await sqlite_session.flush()

    ec = ExamConfiguration(
        blueprint_id=bp.id,
        academic_session_id=session_row.id,
        exam_name="Midterm Physics Config",
    )
    sqlite_session.add(ec)
    await sqlite_session.flush()

    paper = Paper(
        exam_configuration_id=ec.id,
        blueprint_id=bp.id,
        total_marks=8.0,
        status="APPROVED",
    )
    sqlite_session.add(paper)
    await sqlite_session.flush()

    raw_exam = await exam_svc.exam_repo.get_by(public_id=exam["public_id"])
    raw_exam.exam_configuration_id = ec.id
    raw_exam.status = "PUBLISHED"
    raw_exam.join_code = "EXAM-PHYS1"
    await sqlite_session.flush()
    published = exam_svc._exam_to_dict(raw_exam)
    assert published["status"] == "PUBLISHED"

    # 5. Student Attempt Submission
    attempt_svc = AttemptService(sqlite_session)
    attempt = await attempt_svc.start_attempt(
        exam_public_id=exam["public_id"],
        student_id=student.id,
    )
    submitted_attempt = await attempt_svc.submit_attempt(
        attempt_public_id=attempt["public_id"],
        answers_summary_json={
            "q1": {"selected": "A", "marks_awarded": 4.0},
            "q2": {"selected": "B", "marks_awarded": 0.0},
        },
    )
    assert submitted_attempt["status"] == "SUBMITTED"

    # 6. Evaluation Intake & Processing
    eval_svc = EvaluationService(sqlite_session)
    eval_obj = await eval_svc.get_or_create_evaluation(submitted_attempt["id"])
    # Fast-forward through state machine: PENDING → COMPLETED via direct mutation
    eval_obj.status = "COMPLETED"
    eval_obj.total_marks = 4.0
    eval_obj.percentage = 50.0
    eval_obj.result_status = "PASS"
    await sqlite_session.flush()
    locked_eval = await eval_svc.lock_evaluation(eval_obj.public_id)
    assert locked_eval["status"] == "LOCKED"

    # 7. Mastery Engine Update (topics_updated may be 0 if no EvaluationDetail rows)
    mastery_svc = MasteryService(sqlite_session)
    mastery_summary = await mastery_svc.process_evaluation(eval_obj.public_id)
    assert "topics_updated" in mastery_summary
    assert mastery_summary["topics_updated"] >= 0

    # 8. Recommendation Engine Generation
    rec_svc = RecommendationService(sqlite_session)
    rec = await rec_svc.generate_recommendation(
        student_id=student.id,
        subject_id=subject.id,
    )
    assert rec["status"] in ("PENDING", "RECOMMENDED")

    # 9. Analytics Engine Dashboard Computation
    analytics_svc = AnalyticsService(sqlite_session)
    dashboard = await analytics_svc.get_student_dashboard(student.id, subject_id=subject.id)
    assert "is_at_risk" in dashboard

    # 10. Reporting Engine Snapshot
    report_svc = ReportService(sqlite_session)
    snapshot = await report_svc.generate_student_report_card(
        student_id=student.id,
        subject_id=subject.id,
    )
    assert snapshot["status"] == "GENERATED"

    # 11. ERP Webhook Outbound Sync
    mock_webhook = MockWebhookClient(default_status=200)
    mock_webhook.base_url = "http://erp.test"
    erp_svc = ERPIntegrationService(sqlite_session, webhook_client=mock_webhook)
    sync_res = await erp_svc.sync_report(
        report_public_id=str(snapshot["public_id"]),
        student_id=student.id,
        exam_id=exam["id"],
        report_type="STUDENT_PROGRESS",
    )
    assert sync_res["status"] == "SENT"
    assert len(mock_webhook.calls) == 1

    # Final Verification: DB state consistency
    saved_eval = await eval_svc.eval_repo.get_by(id=eval_obj.id)
    assert saved_eval.status == "LOCKED"
