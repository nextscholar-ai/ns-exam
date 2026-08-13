"""
Security Headers Middleware (Phase 21).

Adds standard HTTP security response headers for production hardening:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 1; mode=block
  - Strict-Transport-Security: max-age=31536000; includeSubDomains
  - Content-Security-Policy: default-src 'self'
  - Referrer-Policy: strict-origin-when-cross-origin
"""
from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all outgoing HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        headers["Content-Security-Policy"] = "default-src 'self'"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
