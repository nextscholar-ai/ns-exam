"""
Exception hierarchy for the entire application.

Design:
- `DomainError` and subclasses are raised inside services/domain/ (framework-free).
- The global exception handler (registered in `middleware.py`) translates every
  `DomainError` into the correct HTTP response, so services never import FastAPI
  or know about status codes.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for every business-rule / application error in the system."""

    status_code: int = 400
    error_code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist (or is soft-deleted)."""

    status_code = 404
    error_code = "NOT_FOUND"


class ValidationDomainError(DomainError):
    """Raised for business-rule validation failures (distinct from Pydantic schema errors)."""

    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(DomainError):
    """Raised on uniqueness/state conflicts (e.g. duplicate erp_id, invalid state transition)."""

    status_code = 409
    error_code = "CONFLICT"


class UnauthorizedError(DomainError):
    """Raised when authentication is missing or invalid."""

    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(DomainError):
    """Raised when an authenticated actor lacks permission (RBAC failure)."""

    status_code = 403
    error_code = "FORBIDDEN"


class ExternalServiceError(DomainError):
    """Raised when a call to ERP or another external dependency fails."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class RateLimitedError(DomainError):
    """Raised when a caller exceeds allowed request rate."""

    status_code = 429
    error_code = "RATE_LIMITED"
