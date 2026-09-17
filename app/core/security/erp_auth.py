"""
ERP token validation client (Phase 6 §6.1 — exact contract).

Exam Engine NEVER verifies the ERP JWT signature locally and never shares a
signing secret with ERP (Phase 1 §13 ruling). This call happens exactly once
per login, not per request — after that the client only holds/refreshes the
Exam-Engine JWT.

Phase 4: Uses shared HTTP client with connection pooling.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, UnauthorizedError
from app.core.http import get_http_client
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ERPValidationResult:
    """Exact response shape Exam Engine depends on (Phase 6 §6.1)."""

    valid: bool
    erp_user_id: str
    user_type: str  # STUDENT | TEACHER | SCHOOL_ADMIN | ADMIN
    school_erp_id: str | None
    board_erp_id: str | None
    name: str


@dataclass(frozen=True)
class ERPCredentialResult:
    """Response shape for credential-based ERP login."""

    valid: bool
    erp_user_id: str
    user_type: str
    school_erp_id: str | None
    board_erp_id: str | None
    name: str
    email: str | None
    phone: str | None


class ERPAuthClient:
    """Validates an ERP-issued token against the ERP's own auth service."""

    def __init__(self) -> None:
        self._base_url = settings.erp.base_url
        self._api_key = settings.erp.api_key
        self._validate_path = settings.erp.token_validate_path
        self._login_path = settings.erp.login_path

    async def validate_token(self, erp_token: str) -> ERPValidationResult:
        """
        Validates the ERP-issued JWT against the ERP's own `GET {validate_path}`
        endpoint (real contract, Phase 6 §6.1 — the SCHOOL_ERP service exposes
        `GET /auth/validate-token`).

        Raises UnauthorizedError on any invalid/failed validation - Phase 6
        §12 rule: "ERP validation failure never silently falls back to local
        auth — hard 401." Raises ExternalServiceError if ERP itself is
        unreachable/times out (Phase 6 §23: NOT a silent bypass).
        """
        if not self._base_url:
            raise ExternalServiceError("ERP base URL is not configured")

        url = f"{self._base_url}{self._validate_path}"
        headers = {"Authorization": f"Bearer {erp_token}", "X-API-Key": self._api_key}

        try:
            client = get_http_client()
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("erp_auth.unreachable", error=str(exc))
            raise ExternalServiceError("ERP authentication service unreachable") from exc

        if response.status_code == 401:
            logger.warning("erp_auth.rejected")
            raise UnauthorizedError("ERP rejected the provided token")
        if response.status_code >= 400:
            logger.error("erp_auth.error_status", status_code=response.status_code)
            raise ExternalServiceError(f"ERP auth returned status {response.status_code}")

        try:
            payload = response.json()
        except (ValueError, Exception) as exc:
            logger.error("erp_auth.invalid_json", error=str(exc))
            raise ExternalServiceError("ERP returned invalid response") from exc
        if not payload.get("valid"):
            logger.warning("erp_auth.invalid_payload")
            raise UnauthorizedError("ERP rejected the provided token")

        # SCHOOL_ERP response shape: {"valid", "user_id" (int), "role", "public_id"}.
        erp_user_id = payload.get("user_id") or payload.get("public_id")
        if erp_user_id is None:
            logger.error("erp_auth.missing_user_id")
            raise UnauthorizedError("ERP response missing user identifier")
        logger.info("erp_auth.validated", erp_user_id=erp_user_id)
        return ERPValidationResult(
            valid=True,
            erp_user_id=str(erp_user_id),
            user_type=self._normalize_role(payload.get("role", "")),
            school_erp_id=None,
            board_erp_id=None,
            name=payload.get("public_id", ""),
        )

    async def login_with_credentials(
        self, identifier: str, password: str
    ) -> ERPCredentialResult:
        """
        Validates email/phone + password against the ERP's `POST {login_path}`
        endpoint. The ERP returns user details on success.

        Raises UnauthorizedError on invalid credentials.
        Raises ExternalServiceError if ERP is unreachable.
        """
        if not self._base_url:
            raise ExternalServiceError("ERP base URL is not configured")

        url = f"{self._base_url}{self._login_path}"
        headers = {"X-API-Key": self._api_key}
        body = {"identifier": identifier, "email": identifier, "password": password}

        try:
            client = get_http_client()
            response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("erp_auth.login_unreachable", error=str(exc))
            raise ExternalServiceError("ERP authentication service unreachable") from exc

        if response.status_code == 401:
            logger.warning("erp_auth.login_rejected", identifier=identifier)
            raise UnauthorizedError("Invalid ERP credentials")
        if response.status_code >= 400:
            logger.error("erp_auth.login_error_status", status_code=response.status_code)
            raise ExternalServiceError(f"ERP auth returned status {response.status_code}")

        try:
            payload = response.json()
        except (ValueError, Exception) as exc:
            logger.error("erp_auth.login_invalid_json", error=str(exc))
            raise ExternalServiceError("ERP returned invalid response") from exc

        user_data = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        profile_data = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}

        is_valid = payload.get("valid", bool(payload.get("access_token")))
        if not is_valid:
            logger.warning("erp_auth.login_invalid_payload", identifier=identifier)
            raise UnauthorizedError("Invalid ERP credentials")

        erp_user_id = (
            payload.get("user_id")
            or payload.get("public_id")
            or user_data.get("user_code")
            or user_data.get("id")
        )
        if erp_user_id is None:
            logger.error("erp_auth.login_missing_user_id", identifier=identifier)
            raise UnauthorizedError("ERP response missing user identifier")

        role = payload.get("role") or user_data.get("role") or ""
        name = (
            payload.get("name")
            or profile_data.get("student_name")
            or profile_data.get("teacher_name")
            or profile_data.get("admin_name")
            or user_data.get("user_code")
            or str(erp_user_id)
        )
        email = payload.get("email") or user_data.get("email")
        phone = payload.get("phone") or user_data.get("phone")
        school_id = payload.get("school_erp_id") or profile_data.get("school_id")

        logger.info("erp_auth.login_validated", erp_user_id=str(erp_user_id))
        return ERPCredentialResult(
            valid=True,
            erp_user_id=str(erp_user_id),
            user_type=self._normalize_role(role),
            school_erp_id=school_id,
            board_erp_id=payload.get("board_erp_id"),
            name=name,
            email=email,
            phone=phone,
        )

    @staticmethod
    def _normalize_role(role: str | None) -> str:
        """Map SCHOOL_ERP's lowercase role values to the Exam Engine's
        expected user_type vocabulary. Defaults to ERP_STUDENT."""
        if not role:
            return "ERP_STUDENT"
        return {
            "admin": "ADMIN",
            "teacher": "TEACHER",
            "school_admin": "SCHOOL_ADMIN",
            "student": "ERP_STUDENT",
            "parent": "ERP_STUDENT",
        }.get(role.lower(), "ERP_STUDENT")


erp_auth_client = ERPAuthClient()
