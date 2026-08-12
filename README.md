# Exam Engine — AI-Powered Intelligent Assessment Platform

Phase 1 (Foundation): project scaffold, core infrastructure, all 15 bounded-context
modules wired into the app. See `/mnt/user-data/uploads` phase reports for the full
21-phase plan this follows.

## What's implemented in this phase
- FastAPI app factory (`app/main.py`) — boots with all 15 module routers registered
- Async SQLAlchemy 2.x + PostgreSQL setup (`app/core/db/`)
- `BaseMixin` (dual ID, timestamps, soft delete) + `SnapshotMixin` (ERP snapshot fields)
- Generic `BaseRepository` (soft-delete-aware CRUD)
- Centralized structured JSON logger (`structlog`)
- Global exception hierarchy + handler (`DomainError` → correct HTTP response)
- Request-ID middleware or correlated logs
- JWT primitives + RBAC dependency skeleton + ERP auth client skeleton
- In-process event bus + canonical event name registry
- Alembic wired to async engine, reading `DATABASE_URL` from environment
- Full enterprise folder structure per the report's Phase 5

## Phase 6 — Authentication, Authorization & RBAC (current)
Adds on top of Phase 1:
- **Identity module**: `User`, `Role`, `Permission`, `RefreshToken`, `LoginHistory`, `Company` ORM models (Phase 4 §6.1)
- **Academic module**: `Board`, `School`, `AcademicSession`, `Class`, `Subject`, `Chapter`, `Unit`, `Topic` snapshot models (Phase 4 §6.2)
- **Student/Teacher modules**: `StudentProfile`, `TeacherProfile`, `TeacherSubjectMap` (Phase 4 §6.3)
- Three real login flows: **ERP** (`POST /auth/erp/login`), **Local/External Student** (`POST /auth/local/register`, `POST /auth/local/login`), **Guest** (`POST /auth/guest/start`)
- One JWT format every module trusts (`app/core/security/jwt.py`) — `sub`, `user_type`, `auth_source`, `school_id`, `board_id`, `roles`, `exp`, `jti`
- `get_current_user` / `require_role` / `require_permission` dependencies (`app/core/security/rbac.py`) — zero DB hits per request
- Refresh-token rotation + revocation, guest sessions get no refresh token
- Password hashing (bcrypt via passlib)
- Alembic migration `0001_identity_academic` covering every Phase 4 table
- Seed script for roles/permissions (`scripts/seed_roles_permissions.py`)
- Unit tests: JWT round-trip, password hashing, RBAC dependency logic
- Integration tests: full local register→login→refresh→logout cycle, guest-start scoping (auto-skip if no DB reachable)

## Phase 7 — API Architecture (current)
Adds on top of Phase 6:
- **Standard response envelope** (`ResponseEnvelopeMiddleware`): every `/api/v1/*` success response is wrapped `{"success": true, "data": ..., "meta": {"request_id", "timestamp"}}`; paginated responses get `page`/`page_size`/`total`/`total_pages` in `meta` automatically
- **Standard error format**: `{"success": false, "error": {"code", "message", "details"}, "meta": {...}}` for every `DomainError` *and* FastAPI's own request-validation errors
- **Pagination + whitelisted sorting** (`core/pagination.py`): `apply_sorting()` rejects any `sort_by` not in a per-endpoint whitelist — never raw column injection
- **Real read endpoints** on the Academic module (`/academic/boards|schools|classes|subjects|chapters|units|topics`) — the Phase 7 exit-criteria proof that pagination/sorting/filtering works against a real table
- **Rate limiting** (`core/rate_limit.py`): in-memory token bucket, stricter limits on `/identity/auth/*`
- **Idempotency-key store** (`core/idempotency.py`) — ready for `POST /papers/generate` in Phase 11
- **Async job contract** (`app/jobs/`): `GET /api/v1/jobs/{job_id}` — the polling contract future long-running endpoints (paper generation, OMR batches) will return `202 + job_id` against

## Phase 8 — Repository Layer (current)
Adds on top of Phase 7:
- **`BaseRepository[ModelType]` generalized** (`core/db/base_repository.py`) — every module now inherits `get_by_id`, `get_by_public_id`, `list`, `create`, `update`, `soft_delete`, `hard_delete`
- **Soft-delete filtering is structural** — every query hides `is_deleted=true` rows unless `include_deleted=True` is passed explicitly
- **Row-level School/Board scoping is structural** — `_apply_scope()` filters by `school_id` automatically whenever a school-scoped `current_user` (TEACHER/SCHOOL_ADMIN) is passed; SUPER_ADMIN/ADMIN bypass. A school-scoped caller fetching another school's row gets `None` (→ 404), never a 403 that would leak existence — the primary structural IDOR defense
- **Unit of Work** (`core/db/unit_of_work.py`) — for future multi-repository orchestrations (e.g. Evaluation → Learning Profile → Analytics, all one transaction) that need to share one session explicitly
- **60s in-process TTL cache** (`core/cache.py`) — applied ONLY to the Academic Snapshot tree and RBAC role/permission lookups, per the report's explicit allowlist; transactional data is never cached
- **Academic module rewritten** as the reference pattern (§19) — every entity repository is now a thin `BaseRepository` subclass with a sort-field whitelist, no bespoke pagination code duplicated per entity
- **import-linter contract** (`pyproject.toml`) — fails CI if any module's `service.py` imports `sqlalchemy` directly; verified by hand for this delivery (zero matches)
- **A cross-dialect `GUID` column type** — lets `public_id` use native `UUID` on Postgres but `CHAR(36)` on SQLite, so the repository's soft-delete + scoping guarantees can be proven with a real (if lightweight) database in tests, not just asserted
- **Real functional tests against a real DB** (`tests/unit/test_base_repository.py`, SQLite in-memory) proving: soft-delete hides rows until `include_deleted=True`, school-scoping hides other schools' rows and blocks cross-school `get_by_id` (IDOR), `hard_delete` actually removes rows, admin roles bypass scoping

## Setup — run this locally (step by step)

### 1. Prerequisites
- Python 3.12+
- Docker + Docker Compose (for Postgres)

### 2. Get the code onto your machine
Unzip the project folder wherever you keep your projects.

### 3. Create and activate a virtual environment
```bash
cd exam_engine
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install --upgrade pip
pip install -e ".[dev]"
```
This phase adds `cachetools` (runtime) and `aiosqlite` (dev/test only — lets
the repository tests run against a real database with zero setup).

### 5. Configure environment
```bash
cp .env.example .env
```
Set a real `JWT_SECRET`.

### 6. Start PostgreSQL, migrate, seed
```bash
docker compose up -d postgres
alembic upgrade head
python -m scripts.seed_roles_permissions
```

### 7. Run the app
```bash
uvicorn app.main:app --reload
```

### 8. Run tests — including the new repository tests against a real DB
```bash
pytest -v
pytest tests/unit/test_base_repository.py -v   # soft-delete + scoping, against real SQLite
```
These need zero setup (no Postgres, no Docker) — the fixture spins up an
in-memory SQLite database per test.

### 9. Check the import-linter contract
```bash
lint-imports
```
Confirms no `service.py` file imports `sqlalchemy` directly.

## Running with Docker only (alternative to steps 3–7)
```bash
cp .env.example .env
docker compose up --build -d postgres
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m scripts.seed_roles_permissions
docker compose up
```

## Project layout
```
exam_engine/
├── app/
│   ├── core/
│   │   ├── db/
│   │   │   ├── base_repository.py    # generic contract ← Phase 8
│   │   │   ├── unit_of_work.py       # UoW pattern ← Phase 8
│   │   │   └── base_model.py         # + cross-dialect GUID type ← Phase 8
│   │   ├── cache.py                   # TTL cache wrapper ← Phase 8
│   │   ├── middleware.py
│   │   ├── pagination.py
│   │   ├── rate_limit.py
│   │   └── security/
│   ├── jobs/
│   ├── modules/
│   │   ├── academic/                  # rewritten as THE reference pattern ← Phase 8
│   │   ├── identity/                  # role/permission lookups now cached ← Phase 8
│   │   └── ...
│   └── api/v1/router.py
├── alembic/versions/0001_identity_academic.py
├── scripts/seed_roles_permissions.py
├── tests/
│   └── unit/
│       ├── conftest.py                # sqlite_session fixture ← Phase 8
│       └── test_base_repository.py    # real DB tests ← Phase 8
└── docker-compose.yml
```

## What's next (Phase 9 onward)
Phase 9 (Service Layer) formalizes the business-logic layer pattern
`IdentityService`/`AcademicSnapshotService` already demonstrate, before the
feature modules (Question Bank, Blueprint/Paper Generation, Exam
Management...) get built on top of both layers.

