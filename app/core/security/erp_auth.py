"""
ERP token validation client.

Per Phase 1 §13 ruling: "ERP Auth = token validation via ERP API call, not
shared-secret local JWT verification. Exam Engine never sees or checks
passwords for ERP users." Full request/response contract, retries, and
caching strategy are finalized in Phase 6 - this is the Phase-1 skeleton so
`core/security/rbac.py` has a stable interface to depend on.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, UnauthorizedError
from app.core.logging import get_logger

logger = get_logger(__name__)


class ERPAuthClient:
    """Validates an ERP-issued token against the ERP's own auth service."""

    def __init__(self) -> None:
        self._base_url = settings.erp.base_url
        self._api_key = settings.erp.api_key
        self._validate_path = settings.erp.token_validate_path

    async def validate_token(self, erp_token: str) -> dict:
        """
        Returns the ERP user payload (erp user id, role, school, etc.) on success.
        Raises UnauthorizedError if the token is rejected by ERP, or
        ExternalServiceError if ERP itself is unreachable.
        """
        if not self._base_url:
            # Foundation phase: ERP integration not wired to a real endpoint yet.
            raise ExternalServiceError("ERP base URL is not configured")

        url = f"{self._base_url}{self._validate_path}"
        headers = {"Authorization": f"Bearer {erp_token}", "X-API-Key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("erp_auth.unreachable", error=str(exc))
            raise ExternalServiceError("ERP authentication service unreachable") from exc

        if response.status_code == 401:
            raise UnauthorizedError("ERP rejected the provided token")
        if response.status_code >= 400:
            raise ExternalServiceError(f"ERP auth returned status {response.status_code}")

        return response.json()


erp_auth_client = ERPAuthClient()
