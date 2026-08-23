"""
SUPER_ADMIN role API tests.

SUPER_ADMIN has full access to every endpoint — bypasses all RBAC checks.
Tests verify: auth-protected endpoints accessible, admin-only endpoints accessible,
row-level scoping bypassed, and error paths.
"""
from __future__ import annotations

import pytest

from tests.integration.test_helpers import (
    super_admin_token,
    auth_header,
)


@pytest.mark.asyncio
class TestSuperAdminAuthEndpoints:
    """SUPER_ADMIN can access all identity/auth endpoints."""

    async def test_me_returns_profile(self, api):
        token = super_admin_token()
        resp = await api.get("/api/v1/identity/auth/me", headers=auth_header(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_type"] == "SUPER_ADMIN"
        assert "SUPER_ADMIN" in data["roles"]

    async def test_me_without_token_returns_401(self, api):
        resp = await api.get("/api/v1/identity/auth/me")
        assert resp.status_code == 401

    async def test_me_with_invalid_token_returns_401(self, api):
        resp = await api.get(
            "/api/v1/identity/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    async def test_local_register_creates_external_student(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": "sa_test@example.com", "password": "Test12345", "name": "SA Test"},
        )
        assert resp.status_code in (201, 409)

    async def test_local_login_with_valid_credentials(self, api):
        email = "sa_login_test@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "SA Login"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"]

    async def test_local_login_wrong_password_returns_401(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": "nonexistent@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_guest_start_works_for_admin(self, api):
        resp = await api.post(
            "/api/v1/identity/auth/guest/start", json={"name": "Admin Guest"}
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["guest_pin"]

    async def test_token_refresh_cycle(self, api):
        email = "sa_refresh@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "SA Refresh"},
        )
        login = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "Test12345"},
        )
        refresh_token = login.json()["data"]["refresh_token"]
        resp = await api.post(
            "/api/v1/identity/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
class TestSuperAdminIntegrationModule:
    """SUPER_ADMIN can access integration (admin-only) endpoints."""

    async def test_sync_logs_accessible(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/integration/sync-logs", headers=auth_header(token)
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_sync_status_accessible(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/integration/sync/status", headers=auth_header(token)
        )
        assert resp.status_code == 200

    async def test_sync_logs_inbound_accessible(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/integration/sync/logs", headers=auth_header(token)
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSuperAdminNotificationsModule:
    """SUPER_ADMIN can access notification (admin-only) endpoints."""

    async def test_notification_logs_accessible(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


@pytest.mark.asyncio
class TestSuperAdminJobsModule:
    """SUPER_ADMIN can access jobs endpoints."""

    async def test_list_jobs(self, api):
        token = super_admin_token()
        resp = await api.get("/api/v1/jobs/", headers=auth_header(token))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_get_nonexistent_job_returns_404(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/jobs/nonexistent-id-999", headers=auth_header(token)
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestSuperAdminQuestionBank:
    """SUPER_ADMIN can create/manage questions."""

    async def test_search_questions_empty(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/question_bank", headers=auth_header(token)
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_create_objective_question(self, api):
        token = super_admin_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "What is 2+2?",
                "options": [{"label": "A", "text": "3"}, {"label": "B", "text": "4"}, {"label": "C", "text": "5"}, {"label": "D", "text": "6"}],
                "correct_option": "B",
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code == 201

    async def test_create_subjective_question(self, api):
        token = super_admin_token()
        resp = await api.post(
            "/api/v1/question_bank/subjective",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text": "Explain photosynthesis.",
                "model_answer_text": "Photosynthesis is the process by which plants convert light energy into chemical energy.",
                "max_marks": 5,
                "difficulty": "MEDIUM",
                "bloom_level": "UNDERSTAND",
                "marks": 5,
            },
        )
        assert resp.status_code == 201

    async def test_create_fill_blank_question(self, api):
        token = super_admin_token()
        resp = await api.post(
            "/api/v1/question_bank/fill-blank",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "primary_chapter_id": 1,
                "question_text_with_blanks": "The capital of France is ___.",
                "correct_answers": ["Paris"],
                "difficulty": "EASY",
                "bloom_level": "REMEMBER",
                "marks": 1,
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestSuperAdminBlueprintModule:
    """SUPER_ADMIN can create blueprints and exam configs."""

    async def test_create_blueprint(self, api):
        token = super_admin_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints",
            headers=auth_header(token),
            json={
                "board_id": 1,
                "class_id": 1,
                "subject_id": 1,
                "name": "Test Blueprint",
                "total_marks": 50,
                "duration_minutes": 120,
                "sections": [
                    {
                        "section_label": "Section A",
                        "question_type": "OBJECTIVE",
                        "section_marks": 50,
                        "question_count": 25,
                    }
                ],
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
class TestSuperAdminAcademicEndpoints:
    """SUPER_ADMIN can read academic reference data."""

    async def test_list_boards(self, api):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_list_schools(self, api):
        resp = await api.get("/api/v1/academic/schools")
        assert resp.status_code == 200

    async def test_list_classes(self, api):
        resp = await api.get("/api/v1/academic/classes")
        assert resp.status_code == 200

    async def test_list_subjects(self, api):
        resp = await api.get("/api/v1/academic/subjects")
        assert resp.status_code == 200

    async def test_list_chapters(self, api):
        resp = await api.get("/api/v1/academic/chapters")
        assert resp.status_code == 200

    async def test_list_units(self, api):
        resp = await api.get("/api/v1/academic/units")
        assert resp.status_code == 200

    async def test_list_topics(self, api):
        resp = await api.get("/api/v1/academic/topics")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSuperAdminLearningProfile:
    """SUPER_ADMIN can access learning profile endpoints."""

    async def test_learning_profile_requires_auth(self, api):
        resp = await api.get("/api/v1/learning_profile/1")
        assert resp.status_code == 401

    async def test_learning_profile_accessible_with_token(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/learning_profile/1", headers=auth_header(token)
        )
        # May return 200 or 404 depending on data - but NOT 401
        assert resp.status_code != 401


@pytest.mark.asyncio
class TestSuperAdminErrorHandling:
    """SUPER_ADMIN gets proper error responses."""

    async def test_404_for_nonexistent_endpoint(self, api):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/nonexistent/endpoint", headers=auth_header(token)
        )
        assert resp.status_code == 404

    async def test_405_for_wrong_method(self, api):
        token = super_admin_token()
        resp = await api.put(
            "/api/v1/identity/auth/me", headers=auth_header(token)
        )
        assert resp.status_code == 405
