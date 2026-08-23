"""
Error handling testing across ALL modules.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_helpers import (
    teacher_token,
    auth_header,
)


class TestIdentityModuleErrors:

    @pytest.mark.asyncio
    async def test_register_existing_email_returns_409(self, api: AsyncClient):
        email = "dup_test@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Dup"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "Dup2"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": "weak@example.com", "password": "123", "name": "Weak"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, api: AsyncClient):
        email = "wrongpw@example.com"
        await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": email, "password": "Test12345", "name": "WrongPW"},
        )
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": email, "password": "WrongPassword"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_returns_401(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/local/login",
            json={"email": "nonexistent@example.com", "password": "Test12345"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_401(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/refresh",
            json={"refresh_token": "invalid-refresh-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/logout",
            json={"refresh_token": "some-token"},
        )
        assert resp.status_code == 401


class TestAcademicModuleErrors:

    @pytest.mark.asyncio
    async def test_invalid_sort_by_field_returns_422(self, api: AsyncClient):
        resp = await api.get("/api/v1/academic/boards?sort_by=not_a_real_column")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_page_size_returns_422(self, api: AsyncClient):
        resp = await api.get("/api/v1/academic/boards?page_size=99999")
        assert resp.status_code in (422, 200)


class TestQuestionBankErrors:

    @pytest.mark.asyncio
    async def test_create_question_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.post("/api/v1/question_bank/objective", json={})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_question_missing_fields_returns_422(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/objective", json={}, headers=auth_header(token)
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_nonexistent_question_returns_404(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/question_bank/00000000-0000-0000-0000-000000000000",
            headers=auth_header(token),
        )
        assert resp.status_code == 404


class TestBlueprintErrors:

    @pytest.mark.asyncio
    async def test_create_blueprint_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.post("/api/v1/blueprint/blueprints", json={})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_blueprint_missing_fields_returns_422(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/blueprint/blueprints", json={}, headers=auth_header(token)
        )
        assert resp.status_code == 422


class TestExamManagementErrors:

    @pytest.mark.asyncio
    async def test_create_exam_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.post("/api/v1/exam_management/exams", json={})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_join_exam_invalid_code_returns_404(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/exam_management/exams/join",
            json={"join_code": "INVALID123", "guest_name": "Test"},
        )
        assert resp.status_code in (404, 400)


class TestJobsErrors:

    @pytest.mark.asyncio
    async def test_access_jobs_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.get("/api/v1/jobs/")
        assert resp.status_code == 401


class TestIntegrationErrors:

    @pytest.mark.asyncio
    async def test_sync_logs_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.get("/api/v1/integration/sync-logs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_status_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.get("/api/v1/integration/sync/status")
        assert resp.status_code == 401


class TestNotificationErrors:

    @pytest.mark.asyncio
    async def test_access_logs_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.get("/api/v1/notifications/logs")
        assert resp.status_code == 401


class TestLearningProfileErrors:

    @pytest.mark.asyncio
    async def test_access_without_auth_returns_401(self, api: AsyncClient):
        resp = await api.get("/api/v1/learning_profile/1")
        assert resp.status_code == 401


class TestResponseEnvelopeVerification:

    @pytest.mark.asyncio
    async def test_success_response_envelope(self, api: AsyncClient):
        resp = await api.get("/api/v1/academic/boards")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "meta" in data

    @pytest.mark.asyncio
    async def test_error_404_envelope(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.get(
            "/api/v1/question_bank/00000000-0000-0000-0000-000000000000",
            headers=auth_header(token),
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data.get("success") is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_error_422_envelope(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/local/register",
            json={"email": "bad"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data.get("success") is False

    @pytest.mark.asyncio
    async def test_error_401_envelope(self, api: AsyncClient):
        resp = await api.get("/api/v1/notifications/logs")
        assert resp.status_code == 401
        data = resp.json()
        assert data.get("success") is False
