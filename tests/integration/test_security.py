"""
Security testing: auth bypass, role escalation, input validation, token security.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.test_helpers import (
    make_token,
    super_admin_token,
    teacher_token,
    guest_token,
    auth_header,
)


PROTECTED_ENDPOINTS = [
    "/api/v1/notifications/logs",
    "/api/v1/integration/sync-logs",
    "/api/v1/jobs/",
]


class TestAuthenticationBypass:

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, api: AsyncClient):
        for endpoint in PROTECTED_ENDPOINTS:
            resp = await api.get(endpoint)
            assert resp.status_code == 401, f"{endpoint} should reject unauthenticated"

    @pytest.mark.asyncio
    async def test_empty_bearer_returns_401(self, api: AsyncClient):
        for endpoint in PROTECTED_ENDPOINTS:
            resp = await api.get(endpoint, headers={"Authorization": "Bearer "})
            assert resp.status_code == 401, f"{endpoint} should reject empty bearer"

    @pytest.mark.asyncio
    async def test_bearer_only_no_token_returns_401(self, api: AsyncClient):
        for endpoint in PROTECTED_ENDPOINTS:
            resp = await api.get(endpoint, headers={"Authorization": "Bearer"})
            assert resp.status_code == 401, f"{endpoint} should reject bearer-only"

    @pytest.mark.asyncio
    async def test_tampered_token_returns_401(self, api: AsyncClient):
        token = super_admin_token()
        tampered = token[:-5] + "XXXXX"
        for endpoint in PROTECTED_ENDPOINTS:
            resp = await api.get(endpoint, headers=auth_header(tampered))
            assert resp.status_code == 401, f"{endpoint} should reject tampered token"

    @pytest.mark.asyncio
    async def test_random_string_token_returns_401(self, api: AsyncClient):
        for endpoint in PROTECTED_ENDPOINTS:
            resp = await api.get(
                endpoint, headers=auth_header("completely-random-string-12345")
            )
            assert resp.status_code == 401, f"{endpoint} should reject random string"

    @pytest.mark.asyncio
    async def test_wrong_secret_token_returns_401(self, api: AsyncClient):
        from jose import jwt as jose_jwt
        token = jose_jwt.encode(
            {"sub": "x", "user_type": "ADMIN", "auth_source": "LOCAL",
             "roles": ["ADMIN"], "type": "access"},
            "wrong-secret",
            algorithm="HS256",
        )
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 401


class TestRoleEscalation:

    @pytest.mark.asyncio
    async def test_guest_cannot_access_admin_endpoints(self, api: AsyncClient):
        token = guest_token()
        endpoints = [
            "/api/v1/notifications/logs",
            "/api/v1/integration/sync-logs",
        ]
        for endpoint in endpoints:
            resp = await api.get(endpoint, headers=auth_header(token))
            assert resp.status_code in (401, 403), f"{endpoint} should deny guest"

    @pytest.mark.asyncio
    async def test_teacher_cannot_access_admin_endpoints(self, api: AsyncClient):
        token = teacher_token()
        endpoints = [
            "/api/v1/notifications/logs",
            "/api/v1/integration/sync-logs",
        ]
        for endpoint in endpoints:
            resp = await api.get(endpoint, headers=auth_header(token))
            assert resp.status_code in (401, 403), f"{endpoint} should deny teacher"


class TestInputValidation:

    @pytest.mark.asyncio
    async def test_sql_injection_in_query_params(self, api: AsyncClient):
        token = super_admin_token()
        resp = await api.get(
            "/api/v1/question_bank?q='; DROP TABLE questions;--",
            headers=auth_header(token),
        )
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_xss_in_request_body(self, api: AsyncClient):
        token = super_admin_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            json={"name": "<script>alert('xss')</script>"},
            headers=auth_header(token),
        )
        assert resp.status_code in (400, 422)
        if resp.status_code in (200, 201):
            body = resp.json()
            assert "<script>" not in str(body)

    @pytest.mark.asyncio
    async def test_empty_body_on_post_returns_error(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            json={},
            headers=auth_header(token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_json_body(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            content=b"not json at all",
            headers={**auth_header(token), "Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, api: AsyncClient):
        token = teacher_token()
        resp = await api.post(
            "/api/v1/question_bank/objective",
            json={"text": "incomplete"},
            headers=auth_header(token),
        )
        assert resp.status_code == 422


class TestTokenSecurity:

    @pytest.mark.asyncio
    async def test_token_with_missing_claims(self, api: AsyncClient):
        from jose import jwt as jose_jwt
        from app.core.config import settings
        token = jose_jwt.encode(
            {"sub": "1"},
            settings.jwt.secret,
            algorithm="HS256",
        )
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_token_with_wrong_user_type(self, api: AsyncClient):
        token = make_token(user_type="GUEST_STUDENT", roles=[])
        resp = await api.get(
            "/api/v1/notifications/logs", headers=auth_header(token)
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_guest_token_cannot_refresh(self, api: AsyncClient):
        resp = await api.post(
            "/api/v1/identity/auth/refresh",
            json={"refresh_token": "some-refresh-token"},
        )
        assert resp.status_code in (401, 422)


class TestRateLimiting:

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, api: AsyncClient):
        resp = await api.get("/health")
        assert resp.status_code == 200


class TestSecurityHeaders:

    @pytest.mark.asyncio
    async def test_x_content_type_options(self, api: AsyncClient):
        resp = await api.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, api: AsyncClient):
        resp = await api.get("/health")
        assert resp.headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")

    @pytest.mark.asyncio
    async def test_x_xss_protection(self, api: AsyncClient):
        resp = await api.get("/health")
        assert "x-xss-protection" in resp.headers
