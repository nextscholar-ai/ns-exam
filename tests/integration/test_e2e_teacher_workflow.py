"""
Phase 20 — End-to-End Teacher Assessment Workflow Integration Test.

Tests teacher domain cycle:
  Academic Setup → Question Bank → Blueprint Creation → Exam Management →
  Exam Publishing → Student Attempt → Subjective Evaluation Entry →
  Class Analytics Overview.
"""
from __future__ import annotations

import pytest

from app.modules.academic.models import Board, Chapter, Class, School, Subject, Topic
from app.modules.analytics.service import AnalyticsService
from app.modules.blueprint.schemas import BlueprintCreate, BlueprintSectionCreate
from app.modules.blueprint.service import BlueprintService
from app.modules.evaluation.service import EvaluationService, SubjectiveEvaluationService
from app.modules.exam_management.schemas import ExamCreate
from app.modules.exam_management.service import AttemptService, ExamService
from app.modules.identity.models import User
from app.modules.question_bank.schemas import SubjectiveQuestionCreate
from app.modules.question_bank.service import QuestionBankService
from app.modules.student.models import StudentProfile
from app.modules.teacher.models import TeacherProfile


@pytest.mark.asyncio
async def test_e2e_teacher_blueprint_paper_grading_workflow(sqlite_session):
    """
    End-to-end integration test verifying teacher operations across all domains.
    """
    from datetime import date

    from app.modules.academic.models import AcademicSession, Unit
    from app.modules.blueprint.models import Blueprint as BPModel, ExamConfiguration
    from app.modules.paper_generation.models import Paper

    # 1. Academic Setup
    board = Board(name="State Board", code="SB_E2E", erp_id="ERP_SB_E2E")
    sqlite_session.add(board)
    await sqlite_session.flush()

    school = School(board_id=board.id, name="City High School", erp_id="ERP_CHS_E2E")
    sqlite_session.add(school)
    await sqlite_session.flush()

    cls = Class(school_id=school.id, name="Class 12", erp_id="ERP_C12_E2E")
    sqlite_session.add(cls)
    await sqlite_session.flush()

    subject = Subject(board_id=board.id, class_id=cls.id, name="Chemistry", erp_id="ERP_CHEM_E2E")
    sqlite_session.add(subject)
    await sqlite_session.flush()

    chapter = Chapter(subject_id=subject.id, name="Organic Chemistry", erp_id="ERP_OCH_E2E")
    sqlite_session.add(chapter)
    await sqlite_session.flush()

    unit = Unit(chapter_id=chapter.id, name="Organic Chemistry Unit 1", erp_id="ERP_U1_CHEM_E2E")
    sqlite_session.add(unit)
    await sqlite_session.flush()

    topic = Topic(unit_id=unit.id, name="Alcohols & Ethers", erp_id="ERP_ALC_E2E")
    sqlite_session.add(topic)
    await sqlite_session.flush()

    # 2. Teacher Profile
    t_user = User(
        email="teacher_e2e@ns-exam.com",
        password_hash="hashed_pw",
        user_type="TEACHER",
        auth_source="LOCAL",
    )
    sqlite_session.add(t_user)
    await sqlite_session.flush()

    teacher = TeacherProfile(
        user_id=t_user.id,
        name="E2E Teacher",
        erp_teacher_id="EMP_T_001",
        erp_id="EMP_T_001",
        school_id=school.id,
    )
    sqlite_session.add(teacher)
    await sqlite_session.flush()

    # 3. Question Bank Setup (Subjective)
    qb_svc = QuestionBankService(sqlite_session)
    q_subj = await qb_svc.create_subjective_question(
        SubjectiveQuestionCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subject.id,
            primary_chapter_id=chapter.id,
            primary_unit_id=unit.id,
            primary_topic_id=topic.id,
            question_text="Explain the mechanism of dehydration of ethanol.",
            max_marks=5.0,
            difficulty="HARD",
        )
    )
    assert q_subj is not None

    # 4. Blueprint Creation using BlueprintCreate DTO
    blueprint_svc = BlueprintService(sqlite_session)
    blueprint = await blueprint_svc.create_blueprint(
        BlueprintCreate(
            board_id=board.id,
            class_id=cls.id,
            subject_id=subject.id,
            name="Class 12 Chemistry Assessment Blueprint",
            total_marks=5.0,
            duration_minutes=60,
            sections=[
                BlueprintSectionCreate(
                    section_label="A",
                    question_type="SUBJECTIVE",
                    section_marks=5.0,
                    question_count=1,
                )
            ],
        )
    )
    assert blueprint["public_id"] is not None

    # 5. Exam Creation & Publishing (direct state mutation for E2E simplicity)
    exam_svc = ExamService(sqlite_session)
    exam = await exam_svc.create_exam(
        ExamCreate(
            board_id=board.id,
            school_id=school.id,
            class_id=cls.id,
            subject_id=subject.id,
            title="Class 12 Chemistry Term Exam",
        )
    )

    # Seed AcademicSession + ExamConfiguration + Paper for start_attempt
    session_row = AcademicSession(
        school_id=school.id,
        name="2026-27",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        is_current=True,
        erp_id="ERP_SES_CHEM_E2E",
    )
    sqlite_session.add(session_row)
    await sqlite_session.flush()

    bp_orm = BPModel(
        board_id=board.id,
        class_id=cls.id,
        subject_id=subject.id,
        name="Chem BP ORM",
        total_marks=5.0,
        duration_minutes=60,
    )
    sqlite_session.add(bp_orm)
    await sqlite_session.flush()

    ec = ExamConfiguration(
        blueprint_id=bp_orm.id,
        academic_session_id=session_row.id,
        exam_name="Chem Exam Config",
    )
    sqlite_session.add(ec)
    await sqlite_session.flush()

    paper_orm = Paper(
        exam_configuration_id=ec.id,
        blueprint_id=bp_orm.id,
        total_marks=5.0,
        status="APPROVED",
    )
    sqlite_session.add(paper_orm)
    await sqlite_session.flush()

    raw_exam = await exam_svc.exam_repo.get_by(public_id=exam["public_id"])
    raw_exam.exam_configuration_id = ec.id
    raw_exam.status = "PUBLISHED"
    raw_exam.join_code = "EXAM-CHEM12"
    await sqlite_session.flush()
    published_exam = exam_svc._exam_to_dict(raw_exam)
    assert published_exam["status"] == "PUBLISHED"

    # 6. Student Setup & Attempt
    s_user = User(
        email="s_tech@exam.com",
        password_hash="pw",
        user_type="EXTERNAL_STUDENT",
        auth_source="LOCAL",
    )
    sqlite_session.add(s_user)
    await sqlite_session.flush()

    student = StudentProfile(
        user_id=s_user.id,
        name="S",
        student_type="EXTERNAL",
        school_id=school.id,
        board_id=board.id,
        class_id=cls.id,
    )
    sqlite_session.add(student)
    await sqlite_session.flush()

    attempt_svc = AttemptService(sqlite_session)
    attempt = await attempt_svc.start_attempt(exam["public_id"], student.id)
    submitted = await attempt_svc.submit_attempt(
        attempt["public_id"],
        answers_summary_json={"q_subj": {"answer": "mechanism explanation"}},
    )
    assert submitted["status"] == "SUBMITTED"

    # 7. Evaluation: Teacher enters subjective marks via SubjectiveEvaluationService
    eval_svc = EvaluationService(sqlite_session)
    eval_obj = await eval_svc.get_or_create_evaluation(submitted["id"])

    subj_eval_svc = SubjectiveEvaluationService(sqlite_session)
    graded_detail = await subj_eval_svc.enter_subjective_marks(
        evaluation_public_id=eval_obj.public_id,
        question_id=q_subj["id"],
        question_type="SUBJECTIVE",
        marks_obtained=4.5,
        max_marks=5.0,
    )
    assert graded_detail["marks_obtained"] == 4.5

    # 8. Class Analytics Overview
    analytics_svc = AnalyticsService(sqlite_session)
    class_analytics = await analytics_svc.get_class_analytics(
        class_id=cls.id,
        exam_id=exam["id"],
        subject_id=subject.id,
    )
    assert "class_id" in class_analytics
