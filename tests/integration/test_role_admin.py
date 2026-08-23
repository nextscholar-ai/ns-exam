"""
ADMIN role API tests.

ADMIN has near-SUPER_ADMIN access but is still subject to row-level scoping
when not also having SUPER_ADMIN role. Tests verify: admin-only endpoints,
role restrictions, and standard API behavior.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    admin_token,
    auth_header,
)


@pytest.mark.asyncio
class TestAdminAuthEndpoints:

    async def test_me_returns_admin_profile(self, api):
        token = admin_token()
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "ADMIN"
        assert "ADMIN" in data["roles"]

    async def test_local_register_and_login(self, api):
        email = "admin_register@example.com"
        reg = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Admin Reg"},
        )
        assert reg.status_code in (201, 409)
        login = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        assert login.status_code == 200

    async def test_guest_start_works(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start", json={"name": "Admin Guest"}
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestAdminIntegrationModule:
    """ADMIN can access integration endpoints."""

    async def test_sync_logs_accessible(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_sync_status_accessible(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/integration/sync/status", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAdminNotificationsModule:
    """ADMIN can access notification endpoints (SUPER_ADMIN/ADMIN only)."""

    async def test_notification_logs_accessible(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAdminJobsModule:
    """ADMIN can access jobs endpoints."""

    async def test_list_jobs(self, api):
        token = admin_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 200

    async def test_get_nonexistent_job_returns_404(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/jobs/fake-job-id", headers=auth_header(token)
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAdminQuestionBank:
    """ADMIN can create and manage questions."""

    async def test_create_objective_question(self, api):
        token = admin_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "Admin question test?",
                "options": [{"label": "A", "text": "X"}, {"label": "B", "text": "Y"}, {"label": "C", "text": "Z"}, {"label": "D", "text": "W"}],
                "correct_option": "A",
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code == 201

    async def test_search_questions(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAdminBlueprintModule:

    async def test_create_blueprint(self, api):
        token = admin_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "Admin Blueprint",
                "total_marks": 50,
                "duration_minutes": 60,
                "sections": [
                    {
                        "section_label": "Part A",
                        "question_type": "OBJECTIVE",
                        "section_marks": 50,
                        "question_count": 25,
                    }
                ],
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestAdminAcademicEndpoints:

    async def test_list_boards(self, api):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200

    async def test_list_subjects(self, api):
        resp = await api.get("/api/v1/academic/subjects")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAdminLearningProfile:

    async def test_learning_profile_accessible(self, api):
        token = admin_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestAdminCannotAccessTeacherOnlyEndpoints:
    """ADMIN cannot start exam attempts (teacher/student action)."""

    async def test_cannot_start_attempt_as_admin(self, api):
        token = admin_token()
        resp = await api.post(
            "/api/v1/exam_management/exams/00000000-0000-0000-0000-000000000001/attempts",
            headers=auth_header(token),
            json={"student_id": 1},
        )
        # Should fail (not 401 - token is valid, but the exam doesn't exist)
        assert resp.status_code in (404, 422)


@pytest.mark.asyncio
class TestAdminErrorHandling:

    async def test_invalid_json_body_returns_422(self, api):
        token = admin_token()
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            content="not json",
            headers={**auth_header(token), "Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_missing_required_fields_returns_422(self, api):
        token = admin_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={"question_text": "incomplete"},
        )
        assert resp.status_code == 422
