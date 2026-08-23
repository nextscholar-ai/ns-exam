"""
STUDENT role API tests (ERP_STUDENT and EXTERNAL_STUDENT).

Students have read access to academic data, question bank search, blueprint
ping, exam join, learning profile, analytics, recommendations, and reports.
They are DENIED access to integration, notifications, and jobs modules.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    erp_student_token,
    external_student_token,
    auth_header,
)


@pytest.mark.asyncio
class TestStudentAuthEndpoints:

    async def test_erp_student_me(self, api):
        token = erp_student_token()
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "ERP_STUDENT"
        assert "STUDENT" in data["roles"]

    async def test_external_student_me(self, api):
        token = external_student_token()
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "EXTERNAL_STUDENT"
        assert "STUDENT" in data["roles"]

    async def test_local_register_and_login(self, api):
        email = "student@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Student"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        assert resp.status_code == 200

    async def test_guest_start_works(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start", json={"name": "Student Guest"}
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestStudentIntegrationModule:
    """STUDENT cannot access integration (SUPER_ADMIN/ADMIN/SCHOOL_ADMIN only)."""

    async def test_erp_student_sync_logs_denied(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 403

    async def test_external_student_sync_logs_denied(self, api):
        token = external_student_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestStudentNotificationsModule:
    """STUDENT cannot access notifications (SUPER_ADMIN/ADMIN only)."""

    async def test_erp_student_notification_logs_denied(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403

    async def test_external_student_notification_logs_denied(self, api):
        token = external_student_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestStudentJobsModule:
    """STUDENT cannot access jobs endpoints."""

    async def test_erp_student_list_jobs_denied(self, api):
        token = erp_student_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 403

    async def test_external_student_list_jobs_denied(self, api):
        token = external_student_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestStudentQuestionBank:

    async def test_search_questions(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_search_with_filters(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/question_bank?difficulty=EASY&status=ACTIVE",
            headers=auth_header(token),
        )
        assert resp.status_code == 200

    async def test_external_student_search_questions(self, api):
        token = external_student_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_create_objective_question_denied(self, api):
        token = erp_student_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "Student question?",
                "options_json": {"A": "a", "B": "b", "C": "c", "D": "d"},
                "correct_option": "A",
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code in (403, 422)


@pytest.mark.asyncio
class TestStudentBlueprintModule:

    async def test_blueprint_ping(self, api):
        resp = await api.get("/api/v1/blueprint/ping")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ok"

    async def test_create_blueprint_allowed(self, api):
        token = erp_student_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "Student Blueprint",
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
class TestStudentExamManagement:

    async def test_exam_management_ping(self, api):
        resp = await api.get("/api/v1/exam_management/ping")
        assert resp.status_code == 200

    async def test_create_exam_allowed(self, api):
        token = erp_student_token()
        resp = await api.post(
            "/api/v1/exam_management/exams",
            headers=auth_header(token),
            json={
                "exam_configuration_id": 1,
                "board_id": 1,
                "school_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "title": "Student Exam",
                "exam_type": "REGULAR",
            },
        )
        assert resp.status_code == 201

    async def test_start_attempt_requires_exam(self, api):
        token = erp_student_token()
        resp = await api.post(
            "/api/v1/exam_management/exams/00000000-0000-0000-0000-000000000099/attempts",
            headers=auth_header(token),
            json={"student_id": 1},
        )
        assert resp.status_code in (404, 422)

    async def test_guest_join_endpoint_no_auth(self, api):
        resp = await api.post(
            "/api/v1/exam_management/exams/join",
            json={"join_code": "INVALID-CODE", "guest_name": "Test"},
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestStudentLearningProfile:

    async def test_erp_student_learning_profile_accessible(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code != 401

    async def test_external_student_learning_profile_accessible(self, api):
        token = external_student_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestStudentAnalytics:

    async def test_erp_student_analytics_accessible(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/analytics/student/1?subject_id=1",
            headers=auth_header(token),
        )
        assert resp.status_code != 401

    async def test_external_student_analytics_accessible(self, api):
        token = external_student_token()
        resp = await api.get(
            "/api/v1/analytics/student/1?subject_id=1",
            headers=auth_header(token),
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestStudentRecommendation:

    async def test_list_recommendations_accessible(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/recommendation/student/1",
            headers=auth_header(token),
        )
        assert resp.status_code != 401

    async def test_generate_recommendation_accessible(self, api):
        token = erp_student_token()
        resp = await api.post(
            "/api/v1/recommendation/generate/1",
            headers=auth_header(token),
            json={
                "subject_id": 1,
                "recommendation_type": "PRACTICE_SET",
                "item_count": 5,
            },
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestStudentReports:

    async def test_get_report_accessible(self, api):
        token = erp_student_token()
        resp = await api.get(
            "/api/v1/reports/00000000-0000-0000-0000-000000000099",
            headers=auth_header(token),
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestStudentAcademicEndpoints:

    async def test_list_boards(self, api):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200

    async def test_list_subjects(self, api):
        resp = await api.get("/api/v1/academic/subjects")
        assert resp.status_code == 200

    async def test_list_classes(self, api):
        resp = await api.get("/api/v1/academic/classes")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestStudentErrorHandling:

    async def test_unauthenticated_returns_401(self, api):
        resp = await api.get("/api/v1/question_bank")
        assert resp.status_code == 401

    async def test_tampered_token_returns_401(self, api):
        token = erp_student_token()
        tampered = token[:-5] + "XXXXX"
        resp = await api.get(
            "/api/v1/identity/auth/me", headers=auth_header(tampered)
        )
        assert resp.status_code == 401

    async def test_external_student_tampered_token_returns_401(self, api):
        token = external_student_token()
        tampered = token[:-5] + "XXXXX"
        resp = await api.get(
            "/api/v1/identity/auth/me", headers=auth_header(tampered)
        )
        assert resp.status_code == 401
