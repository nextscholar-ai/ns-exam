<div align="center">

# 📝 Exam Engine

### AI-Powered Intelligent Assessment Platform

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Built with:** FastAPI + SQLAlchemy 2.0 (Async) + PostgreSQL + Alembic + Docker

[Features](#-features) • [Tech Stack](#-tech-stack) • [Quick Start](#-quick-start) • [API Docs](#-api-documentation) • [Project Structure](#-project-structure)

</div>

---

## 📖 About the Project

**Exam Engine** is a comprehensive, AI-powered assessment platform designed for educational institutions. It handles the complete lifecycle of academic examinations — from question banking, paper generation, and exam scheduling to student attempts, automated OMR evaluation, mastery tracking, personalized recommendations, analytics dashboards, and reporting.

This is a **backend API** built with modern Python async patterns. It integrates with external ERP systems (School ERP) and supports multiple authentication flows including ERP login, local login, and guest access.

### Why This Project?

- **Fully Async** — Built on FastAPI + asyncpg for high-concurrency, non-blocking I/O
- **Modular Architecture** — 15 bounded-context modules with clean separation
- **AI-Powered** — Automated paper generation, mastery tracking, personalized recommendations
- **Multi-Auth** — ERP, Local, and Guest authentication flows with unified JWT
- **Production Ready** — Docker, health checks, rate limiting, structured logging, test suite

---

## ✨ Features

| Category | Capabilities |
|----------|-------------|
| 👤 **Identity & Auth** | ERP login, Local login/register, Guest access, JWT + refresh tokens, RBAC |
| 🎓 **Academic** | Boards, Schools, Sessions, Classes, Subjects, Chapters, Units, Topics |
| 📋 **Question Bank** | Objective, Subjective, Fill-in-blank questions with versioning |
| 📄 **Paper Generation** | AI-powered paper creation, blueprints, sections, validation |
| 📝 **Exam Management** | Exam lifecycle, scheduling, student assignments, attempts |
| ✅ **Evaluation** | Automated OMR, subjective evaluation, re-evaluation workflow |
| 📊 **Mastery Tracking** | EMA-based topic/chapter/subject mastery scores |
| 🎯 **Recommendations** | Personalized practice recommendations + feedback |
| 📈 **Analytics** | Student & class performance dashboards |
| 📑 **Reports** | Student progress, exam analysis, class performance reports |
| 🔗 **ERP Integration** | Bidirectional sync with School ERP system |
| 🔔 **Notifications** | Email + push notification system |
| ⚙️ **Background Jobs** | Async job infrastructure for long-running tasks |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.12+ |
| **Web Framework** | FastAPI (async) |
| **ASGI Server** | Uvicorn |
| **ORM** | SQLAlchemy 2.0 (Async, mapped_column) |
| **Database** | PostgreSQL 16 (via asyncpg) |
| **Migrations** | Alembic (async) |
| **Validation** | Pydantic v2 + pydantic-settings |
| **Auth/JWT** | python-jose (HS256) + bcrypt |
| **Caching** | cachetools (TTLCache, in-process) |
| **Logging** | structlog (JSON structured) |
| **HTTP Client** | httpx (async, for ERP integration) |
| **Containerization** | Docker + Docker Compose |
| **Testing** | pytest + pytest-asyncio + aiosqlite |
| **Linting** | Ruff + import-linter |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+** installed
- **Docker + Docker Compose** (for PostgreSQL)
- **Git** installed

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-username/exam-engine.git
cd exam-engine
```

### Step 2: Create a Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Open `.env` and set a strong `JWT_SECRET`:

```bash
# Generate a strong secret
python -c "import secrets; print(secrets.token_hex(32))"
```

### Step 5: Start PostgreSQL

```bash
docker compose up -d postgres
```

### Step 6: Run Migrations

```bash
alembic upgrade head
```

### Step 7: Seed User Accounts

```bash
python -m scripts.seed_accounts
```

This creates 5 user accounts with role assignments:

| Role | Email | Password |
|------|-------|----------|
| SUPER_ADMIN | `superadmin@ns-exam.com` | `password123` |
| ADMIN | `admin@ns-exam.com` | `password123` |
| SCHOOL_ADMIN | `schooladmin@ns-exam.com` | `password123` |
| TEACHER | `teacher@ns-exam.com` | `password123` |
| STUDENT | `student@ns-exam.com` | `password123` |

### Step 8: Start the Server

```bash
uvicorn app.main:app --reload
```

### Step 9: Run Tests

```bash
pytest -v
```

Tests run against SQLite in-memory — no external database needed.

---

## 🔐 Authentication

### Three Login Flows

#### 1. Local Login (Email + Password)
```bash
curl -X POST http://localhost:8000/api/v1/identity/auth/local/login \
  -H "Content-Type: application/json" \
  -d '{"email": "student@ns-exam.com", "password": "password123"}'
```

#### 2. Guest Login (No Account Required)
```bash
curl -X POST http://localhost:8000/api/v1/identity/auth/guest/start \
  -H "Content-Type: application/json" \
  -d '{"name": "Guest Student"}'
```
Returns a 4-hour access token + 6-digit PIN for exam re-auth.

#### 3. Local Register (New Account)
```bash
curl -X POST http://localhost:8000/api/v1/identity/auth/local/register \
  -H "Content-Type: application/json" \
  -d '{"email": "new@student.com", "password": "pass1234", "name": "New Student"}'
```

### Token Refresh
```bash
curl -X POST http://localhost:8000/api/v1/identity/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "YOUR_REFRESH_TOKEN"}'
```

### Get Current User
```bash
curl http://localhost:8000/api/v1/identity/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## 📡 API Documentation

Once the server is running, access:

| Resource | URL |
|----------|-----|
| **Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| **Health Check** | [http://localhost:8000/health](http://localhost:8000/health) |
| **DB Health** | [http://localhost:8000/health/db](http://localhost:8000/health/db) |
| **Metrics** | [http://localhost:8000/health/metrics](http://localhost:8000/health/metrics) |

### API Endpoints Overview

| Prefix | Module | Description |
|--------|--------|-------------|
| `/api/v1/identity/*` | Identity | Auth, users, roles, permissions |
| `/api/v1/academic/*` | Academic | Boards, schools, classes, subjects |
| `/api/v1/student/*` | Student | Student profiles |
| `/api/v1/teacher/*` | Teacher | Teacher profiles, subject maps |
| `/api/v1/question-bank/*` | Question Bank | Questions, versions, statistics |
| `/api/v1/blueprint/*` | Blueprint | Paper structure rules |
| `/api/v1/paper-generation/*` | Paper Generation | AI-powered paper creation |
| `/api/v1/exam-management/*` | Exam Management | Exams, attempts, assignments |
| `/api/v1/evaluation/*` | Evaluation | OMR, subjective eval, re-eval |
| `/api/v1/learning-profile/*` | Learning Profile | Mastery tracking |
| `/api/v1/analytics/*` | Analytics | Student & class dashboards |
| `/api/v1/recommendation/*` | Recommendation | Practice recommendations |
| `/api/v1/reports/*` | Reports | Generated reports |
| `/api/v1/storage/*` | Storage | File metadata |
| `/api/v1/integration/*` | Integration | ERP sync, webhooks |
| `/api/v1/notifications/*` | Notifications | Email & push |
| `/api/v1/jobs/*` | Jobs | Background job management |

---

## 📁 Project Structure

```
ns-exam/
├── app/                          # Main application package
│   ├── main.py                   # FastAPI app factory
│   ├── api/v1/router.py          # Central API router
│   │
│   ├── core/                     # Cross-cutting infrastructure
│   │   ├── config.py             # Pydantic Settings
│   │   ├── db/                   # Database layer
│   │   │   ├── base_model.py     # Base, BaseMixin, SnapshotMixin
│   │   │   ├── base_repository.py # Generic CRUD repository
│   │   │   ├── session.py        # Engine, session factory
│   │   │   └── unit_of_work.py   # Unit of Work pattern
│   │   ├── security/             # Auth infrastructure
│   │   │   ├── jwt.py            # JWT creation/decoding
│   │   │   ├── rbac.py           # get_current_user, require_role
│   │   │   ├── password.py       # bcrypt hash/verify
│   │   │   └── erp_auth.py       # ERP token validation
│   │   ├── events/               # In-process pub-sub event bus
│   │   ├── notifications/        # Email + Push notifications
│   │   ├── middleware.py          # Rate limit, request context, response envelope
│   │   ├── pagination.py         # Shared pagination/sorting
│   │   ├── cache.py              # TTL cache wrapper
│   │   └── exceptions.py         # Domain error hierarchy
│   │
│   └── modules/                  # 15 bounded-context modules
│       ├── identity/             # Users, Roles, Permissions, Auth
│       ├── academic/             # Board, School, Session, Class, Subject
│       ├── student/              # Student profiles
│       ├── teacher/              # Teacher profiles
│       ├── question_bank/        # Questions + versioning
│       ├── blueprint/            # Paper structure rules
│       ├── paper_generation/     # AI paper generation
│       ├── exam_management/      # Exam lifecycle
│       ├── evaluation/           # OMR + subjective evaluation
│       ├── learning_profile/     # Mastery engine (EMA)
│       ├── analytics/            # Performance dashboards
│       ├── recommendation/       # Practice recommendations
│       ├── reports/              # Report generation
│       ├── storage/              # File metadata
│       └── integration/          # ERP sync + webhooks
│
├── alembic/                      # Database migrations
│   └── versions/
│       ├── 0001_identity_academic.py
│       └── 9fedf51dd716_*.py
│
├── scripts/                      # Utility scripts
│   └── seed_accounts.py          # Seed user accounts only
│
├── tests/                        # Test suite
│   ├── conftest.py               # Fixtures (SQLite in-memory)
│   ├── unit/                     # 20+ unit test files
│   └── integration/              # E2E auth, API contracts
│
├── Dockerfile                    # Multi-stage production build
├── docker-compose.yml            # PostgreSQL + app services
├── alembic.ini                   # Alembic configuration
├── pyproject.toml                # Project metadata + deps
├── requirements.txt              # Pinned dependencies
├── .env.example                  # Environment template
└── README.md                     # This file
```

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `JWT_SECRET` | ✅ | — | JWT signing secret |
| `JWT_ALGORITHM` | ❌ | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `60` | Access token expiry |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | ❌ | `7` | Refresh token expiry |
| `APP_NAME` | ❌ | `Exam Engine` | Application name |
| `APP_ENV` | ❌ | `development` | Environment mode |
| `APP_DEBUG` | ❌ | `true` | Debug mode |
| `DB_POOL_SIZE` | ❌ | `5` | Connection pool size |
| `DB_MAX_OVERFLOW` | ❌ | `10` | Max overflow connections |
| `DB_ECHO` | ❌ | `false` | Log SQL queries |
| `STORAGE_BACKEND` | ❌ | `local` | File storage backend |
| `STORAGE_BASE_PATH` | ❌ | `./uploads` | Upload directory |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |
| `CORS_ORIGINS` | ❌ | `*` | Comma-separated allowed origins |

---

## 🔒 Security Features

- **Multi-Auth** — ERP, Local, and Guest authentication flows
- **JWT + Refresh Tokens** — Access tokens with rotation + revocation
- **Password Hashing** — bcrypt with salt
- **RBAC** — Role-based access control (SUPER_ADMIN, ADMIN, SCHOOL_ADMIN, TEACHER, STUDENT)
- **Row-Level Security** — School/Board scoping in BaseRepository
- **IDOR Prevention** — Cross-school access returns 404 (not 403)
- **Rate Limiting** — 120 req/min general, 10 req/min on auth endpoints
- **Security Headers** — HSTS, CSP, X-Frame-Options
- **Guest Sessions** — 4-hour tokens, no refresh, 6-digit PIN for re-auth
- **Request Tracing** — UUID-based request IDs

---

## 🧪 Testing

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/unit/test_base_repository.py -v

# Run integration tests
pytest tests/integration/ -v
```

**Test Infrastructure:** Tests use SQLite in-memory databases — no external PostgreSQL needed. The `sqlite_session` fixture spins up a fresh database per test.

---

## 🐳 Docker

### Run with Docker

```bash
# Start PostgreSQL
docker compose up -d postgres

# Run migrations
docker compose run --rm app alembic upgrade head

# Seed accounts
docker compose run --rm app python -m scripts.seed_accounts

# Start full stack
docker compose up
```

### Production Build

```bash
docker compose -f docker-compose.yml up --build
```

---

## 🔗 ERP Integration

Exam Engine integrates with School ERP for bidirectional data sync:

- **Inbound:** ERP pushes academic data (boards, schools, classes, subjects)
- **Outbound:** Exam Engine pushes exam results, analytics back to ERP
- **Auth:** ERP users authenticate via token validation against ERP's `/auth/validate-token`

---

## 🚢 Deployment

### Production Checklist

1. Set a strong `JWT_SECRET`
2. Set `APP_ENV=production` and `APP_DEBUG=false`
3. Configure `CORS_ORIGINS` with your frontend domain
4. Use a production ASGI server (Uvicorn with workers)
5. Set up a reverse proxy (Nginx/Caddy)
6. Configure SSL/TLS
7. Set up database backups
8. Configure log rotation

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">

**Built with ❤️ for Education**

</div>
