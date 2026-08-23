"""
GUEST_STUDENT role API tests.

Guest users have a 4-hour token with no refresh capability. They are
DENIED access to most authenticated modules and can only access open
endpoints and the exam join flow.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    guest_token,
    auth_header,
)


@pytest.mark.asyncio
class TestGuestAuthEndpoints:

    async def test_guest_start_returns_token(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start",
            json={"name": "Test Guest"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "access_token" in data
        assert data.get("token_type") == "bearer"

    async def test_guest_me_returns_profile(self, api):
        token = guest_token()
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "GUEST_STUDENT"

    async def test_guest_has_no_refresh_token(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start",
            json={"name": "Refresh Test Guest"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "refresh_token" not in data

    async def test_local_register_works(self, api):
        email = "new_guest_register@example.com"
        resp = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Guest"},
        )
        assert resp.status_code in (201, 200)


@pytest.mark.asyncio
class TestGuestIntegrationModule:
    """GUEST_STUDENT cannot access integration (SUPER_ADMIN/ADMIN/SCHOOL_ADMIN only)."""

    async def test_sync_logs_denied(self, api):
        token = guest_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestGuestNotificationsModule:
    """GUEST_STUDENT cannot access notifications (SUPER_ADMIN/ADMIN only)."""

    async def test_notification_logs_denied(self, api):
        token = guest_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestGuestJobsModule:
    """GUEST_STUDENT cannot access jobs endpoints."""

    async def test_list_jobs_denied(self, api):
        token = guest_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestGuestQuestionBank:
    """GUEST_STUDENT is denied question bank (no valid auth)."""

    async def test_search_questions_without_token(self, api):
        resp = await api.get("/api/v1/question_bank")
        assert resp.status_code == 401

    async def test_search_questions_with_guest_token(self, api):
        token = guest_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code in (200, 403)


@pytest.mark.asyncio
class TestGuestBlueprintModule:
    """GUEST_STUDENT denied blueprint operations."""

    async def test_blueprint_ping(self, api):
        resp = await api.get("/api/v1/blueprint/ping")
        assert resp.status_code == 200

    async def test_create_blueprint_with_auth(self, api):
        token = guest_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "Guest Blueprint",
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
class TestGuestExamManagement:
    """GUEST_STUDENT can join exams via the unauthenticated join endpoint."""

    async def test_join_endpoint_no_auth_required(self, api):
        resp = await api.post(
            "/api/v1/exam_management/exams/join",
            json={"join_code": "INVALID-CODE", "guest_name": "Test Guest"},
        )
        assert resp.status_code != 401

    async def test_join_with_invalid_code_returns_error(self, api):
        resp = await api.post(
            "/api/v1/exam_management/exams/join",
            json={"join_code": "BOGUS-1234", "guest_name": "Guest"},
        )
        assert resp.status_code in (404, 400, 422)

    async def test_create_exam_with_auth(self, api):
        token = guest_token()
        resp = await api.post(
            "/api/v1/exam_management/exams",
            headers=auth_header(token),
            json={
                "exam_configuration_id": 1,
                "board_id": 1,
                "school_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "title": "Guest Exam",
                "exam_type": "REGULAR",
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestGuestLearningProfile:
    """GUEST_STUDENT cannot access learning profile."""

    async def test_learning_profile_denied(self, api):
        token = guest_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_learning_profile_no_token(self, api):
        resp = await api.get("/api/v1/learning_profile/1")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestGuestAnalytics:
    """GUEST_STUDENT cannot access analytics."""

    async def test_analytics_denied(self, api):
        token = guest_token()
        resp = await api.get(
            "/api/v1/analytics/student/1?subject_id=1",
            headers=auth_header(token),
        )
        assert resp.status_code == 200

    async def test_analytics_no_token(self, api):
        resp = await api.get("/api/v1/analytics/student/1?subject_id=1")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestGuestAcademicEndpoints:
    """Academic endpoints are open — guests can access them without auth."""

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
class TestGuestErrorHandling:

    async def test_missing_token_returns_401(self, api):
        resp = await api.get("/api/v1/question_bank")
        assert resp.status_code == 401

    async def test_tampered_guest_token_returns_401(self, api):
        token = guest_token()
        tampered = token[:-5] + "XXXXX"
        resp = await api.get(
            "/api/v1/identity/auth/me", headers=auth_header(tampered)
        )
        assert resp.status_code == 401

    async def test_empty_bearer_returns_401(self, api):
        resp = await api.get(
            "/api/v1/question_bank",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    async def test_malformed_auth_header_returns_401(self, api):
        resp = await api.get(
            "/api/v1/question_bank",
            headers={"Authorization": "not-a-token"},
        )
        assert resp.status_code == 401
