"""
TEACHER role API tests.

TEACHER is school-scoped and can manage questions, blueprints, exams,
and view student analytics. Tests verify: teacher-specific access,
school scoping, and read-only restrictions.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    teacher_token,
    auth_header,
)


@pytest.mark.asyncio
class TestTeacherAuthEndpoints:

    async def test_me_returns_teacher_profile(self, api):
        token = teacher_token(school_id=1, board_id=1)
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "TEACHER"
        assert data["school_id"] == 1
        assert "TEACHER" in data["roles"]

    async def test_local_register_and_login(self, api):
        email = "teacher@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Teacher"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        assert resp.status_code == 200

    async def test_guest_start_works(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start", json={"name": "Teacher Guest"}
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestTeacherIntegrationModule:
    """TEACHER CANNOT access integration (SUPER_ADMIN/ADMIN/SCHOOL_ADMIN only)."""

    async def test_sync_logs_denied(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestTeacherNotificationsModule:
    """TEACHER CANNOT access notifications (SUPER_ADMIN/ADMIN only)."""

    async def test_notification_logs_denied(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestTeacherJobsModule:
    """TEACHER can access jobs endpoints."""

    async def test_list_jobs(self, api):
        token = teacher_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestTeacherQuestionBank:
    """TEACHER can create and manage questions."""

    async def test_create_objective_question(self, api):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "Teacher question?",
                "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}, {"label": "C", "text": "c"}, {"label": "D", "text": "d"}],
                "correct_option": "A",
                "difficulty": "MEDIUM",
                "bloom_level": "UNDERSTAND",
                "marks": 2,
            },
        )
        assert resp.status_code == 201

    async def test_create_subjective_question(self, api):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/subjective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "Describe the water cycle.",
                "model_answer_text": "The water cycle involves evaporation, condensation, and precipitation.",
                "max_marks": 5,
                "difficulty": "MEDIUM",
                "bloom_level": "UNDERSTAND",
                "marks": 5,
            },
        )
        assert resp.status_code == 201

    async def test_create_fill_blank_question(self, api):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/fill-blank",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text_with_blanks": "The boiling point of water is ___ degrees Celsius.",
                "correct_answers": ["100"],
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code == 201

    async def test_search_questions(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_search_with_filters(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/question_bank?difficulty=EASY&status=ACTIVE",
            headers=auth_header(token),
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestTeacherBlueprintModule:
    """TEACHER can create blueprints."""

    async def test_create_blueprint(self, api):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "Teacher Blueprint",
                "total_marks": 30,
                "duration_minutes": 30,
                "sections": [
                    {
                        "section_label": "Quiz",
                        "question_type": "OBJECTIVE",
                        "section_marks": 30,
                        "question_count": 15,
                    }
                ],
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestTeacherExamManagement:
    """TEACHER can create and manage exams."""

    async def test_create_exam(self, api):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/exam_management/exams",
            headers=auth_header(token),
            json={
                "exam_configuration_id": 1,
                "board_id": 1,
                "school_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "title": "Teacher Exam",
                "exam_type": "REGULAR",
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestTeacherAcademicEndpoints:

    async def test_list_boards(self, api):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200

    async def test_list_subjects(self, api):
        resp = await api.get("/api/v1/academic/subjects")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestTeacherLearningProfile:

    async def test_learning_profile_accessible(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestTeacherAnalytics:

    async def test_student_analytics_accessible(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/analytics/student/1?subject_id=1",
            headers=auth_header(token),
        )
        # May return 200 or 404 depending on data
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestTeacherErrorHandling:

    async def test_unauthenticated_access_denied(self, api):
        resp = await api.get("/api/v1/question_bank")
        assert resp.status_code == 401

    async def test_forbidden_for_admin_endpoints(self, api):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403
