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
    """Raised for business-rule validation failures (distinct from Pydantic schema errors).
    Aliased as `ValidationError` to match Phase 7 §5.3's documented hierarchy name
    (kept as ValidationDomainError internally to avoid shadowing Pydantic's own
    ValidationError)."""

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
    """Raised when an authenticated actor lacks permission (RBAC failure).
    This IS Phase 7 §5.3's `PermissionDeniedError` - see alias below."""

    status_code = 403
    error_code = "PERMISSION_DENIED"


class BusinessRuleError(DomainError):
    """Generic 400-level business-rule violation that doesn't fit NotFound/
    Validation/Conflict/Forbidden (Phase 7 §5.3)."""

    status_code = 400
    error_code = "BUSINESS_RULE_ERROR"


class ExternalServiceError(DomainError):
    """Raised when a call to ERP or another external dependency fails."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class RateLimitedError(DomainError):
    """Raised when a caller exceeds allowed request rate (Phase 7 §5.8)."""

    status_code = 429
    error_code = "RATE_LIMITED"


# Phase 7 §5.3 documents this exact class-name hierarchy - aliases so code can
# use either name interchangeably without duplicating logic.
ValidationError = ValidationDomainError
PermissionDeniedError = ForbiddenError
