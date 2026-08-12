"""Cross-module constants. Keep this tiny - module-specific constants belong
inside that module."""

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200

GUEST_STUDENT_RETENTION_DAYS = 45  # hard-delete cleanup job, Phase 17

REQUEST_ID_HEADER = "X-Request-ID"
