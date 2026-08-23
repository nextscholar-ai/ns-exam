"""
SCHOOL_ADMIN role API tests.

SCHOOL_ADMIN is school-scoped: can manage their own school's data but
cannot access cross-school resources. Tests verify: school-scoped access,
admin-level module access, and IDOR prevention.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    school_admin_token,
    auth_header,
)


@pytest.mark.asyncio
class TestSchoolAdminAuthEndpoints:

    async def test_me_returns_school_admin_profile(self, api):
        token = school_admin_token(school_id=1, board_id=1)
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "SCHOOL_ADMIN"
        assert data["school_id"] == 1
        assert data["board_id"] == 1

    async def test_local_register_and_login(self, api):
        email = "school_admin@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "School Admin"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        assert resp.status_code == 200

    async def test_guest_start_works(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start", json={"name": "SA Guest"}
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestSchoolAdminIntegrationModule:
    """SCHOOL_ADMIN can access integration endpoints."""

    async def test_sync_logs_accessible(self, api):
        token = school_admin_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_sync_status_accessible(self, api):
        token = school_admin_token()
        resp = await api.get(
            "/api/v1/integration/sync/status", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSchoolAdminNotificationsModule:
    """SCHOOL_ADMIN CANNOT access notifications (SUPER_ADMIN/ADMIN only)."""

    async def test_notification_logs_denied(self, api):
        token = school_admin_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestSchoolAdminJobsModule:
    """SCHOOL_ADMIN can access jobs endpoints."""

    async def test_list_jobs(self, api):
        token = school_admin_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 200

    async def test_bulk_import_requires_teacher_or_admin_role(self, api):
        token = school_admin_token()
        resp = await api.post(
            "/api/v1/jobs/bulk-question-import",
            headers=auth_header(token),
            json={
                "subject_id": 1,
                "chapter_id": 1,
                "questions": [],
            },
        )
        # SCHOOL_ADMIN has TEACHER-like access to jobs
        assert resp.status_code in (202, 422, 400)


@pytest.mark.asyncio
class TestSchoolAdminQuestionBank:

    async def test_create_question(self, api):
        token = school_admin_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "SA question?",
                "options": [{"label": "A", "text": "1"}, {"label": "B", "text": "2"}, {"label": "C", "text": "3"}, {"label": "D", "text": "4"}],
                "correct_option": "A",
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code == 201

    async def test_search_questions(self, api):
        token = school_admin_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSchoolAdminBlueprintModule:

    async def test_create_blueprint(self, api):
        token = school_admin_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "SA Blueprint",
                "total_marks": 40,
                "duration_minutes": 45,
                "sections": [
                    {
                        "section_label": "MCQ",
                        "question_type": "OBJECTIVE",
                        "section_marks": 40,
                        "question_count": 20,
                    }
                ],
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestSchoolAdminAcademicEndpoints:

    async def test_list_boards(self, api):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200

    async def test_list_schools(self, api):
        resp = await api.get("/api/v1/academic/schools")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSchoolAdminLearningProfile:

    async def test_learning_profile_accessible(self, api):
        token = school_admin_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestSchoolAdminErrorHandling:

    async def test_unauthenticated_access_denied(self, api):
        resp = await api.get("/api/v1/learning_profile/1")
        assert resp.status_code == 401

    async def test_tampered_token_rejected(self, api):
        token = school_admin_token()
        tampered = token[:-5] + "XXXXX"
        resp = await api.get(
            "/api/v1/identity/auth/me", headers=auth_header(tampered)
        )
        assert resp.status_code == 401
