"""
ERP token validation client (Phase 6 §6.1 — exact contract).

Exam Engine NEVER verifies the ERP JWT signature locally and never shares a
signing secret with ERP (Phase 1 §13 ruling). This call happens exactly once
per login, not per request — after that the client only holds/refreshes the
Exam-Engine JWT.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, UnauthorizedError
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


class ERPAuthClient:
    """Validates an ERP-issued token against the ERP's own auth service."""

    def __init__(self) -> None:
        self._base_url = settings.erp.base_url
        self._api_key = settings.erp.api_key
        self._validate_path = settings.erp.token_validate_path

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
            async with httpx.AsyncClient(timeout=5.0) as client:
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

        payload = response.json()
        if not payload.get("valid"):
            logger.warning("erp_auth.invalid_payload")
            raise UnauthorizedError("ERP rejected the provided token")

        # SCHOOL_ERP response shape: {"valid", "user_id" (int), "role", "public_id"}.
        logger.info("erp_auth.validated", erp_user_id=payload.get("user_id"))
        return ERPValidationResult(
            valid=True,
            erp_user_id=str(payload.get("user_id") or payload.get("public_id")),
            user_type=self._normalize_role(payload.get("role", "")),
            school_erp_id=None,
            board_erp_id=None,
            name=payload.get("public_id", ""),
        )

    @staticmethod
    def _normalize_role(role: str) -> str:
        """Map SCHOOL_ERP's lowercase role values to the Exam Engine's
        expected user_type vocabulary (STUDENT | TEACHER | SCHOOL_ADMIN |
        ADMIN | ERP_STUDENT). Defaults to ERP_STUDENT - Phase 6 §6.1."""
        return {
            "admin": "ADMIN",
            "teacher": "TEACHER",
            "school_admin": "SCHOOL_ADMIN",
            "student": "ERP_STUDENT",
            "parent": "ERP_STUDENT",
        }.get(role.lower(), "ERP_STUDENT")


erp_auth_client = ERPAuthClient()
