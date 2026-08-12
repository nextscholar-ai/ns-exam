"""
Phase 6 §22 integration tests: full local register -> login -> refresh ->
logout cycle, and guest-start scoping. Updated for the Phase 7 §5.2 response
envelope - every success body is `{"success": true, "data": ..., "meta": ...}`.

Need a real (test) Postgres database - skipped automatically if
DATABASE_URL isn't reachable, so `pytest -v` still passes cleanly using only
the unit tests in CI environments without Postgres configured. Point this at
a disposable test DB (e.g. `docker compose up -d postgres`) to actually
exercise it.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db.session import check_db_connection
from app.main import app


@pytest.fixture()
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_full_local_auth_cycle(api_client):
    if not await check_db_connection():
        pytest.skip("No reachable database configured - skipping integration test")

    email = "pytest-user@example.com"
    register_resp = await api_client.post(
        "/api/v1/identity/auth/local/register",
        json={"email": email, "password": "Sup3rSecret1", "name": "Pytest User"},
    )
    assert register_resp.status_code in (201, 409)  # 409 if re-run without cleanup

    login_resp = await api_client.post(
        "/api/v1/identity/auth/local/login",
        json={"email": email, "password": "Sup3rSecret1"},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["success"] is True
    tokens = body["data"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_resp = await api_client.get(
        "/api/v1/identity/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["auth_source"] == "LOCAL"

    refresh_resp = await api_client.post(
        "/api/v1/identity/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()["data"]

    logout_resp = await api_client.post(
        "/api/v1/identity/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout_resp.status_code == 204


@pytest.mark.asyncio
async def test_guest_start_returns_guest_scoped_token(api_client):
    if not await check_db_connection():
        pytest.skip("No reachable database configured - skipping integration test")

    resp = await api_client.post("/api/v1/identity/auth/guest/start", json={"name": "Guest Kid"})
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["access_token"]
    assert "refresh_token" not in body  # guests never get a refresh token (Phase 6 §6.3)
    assert len(body["guest_pin"]) == 6


@pytest.mark.asyncio
async def test_academic_boards_pagination_envelope(api_client):
    """Phase 7 exit criteria: pagination/sorting works against a real table
    (Academic, from Phase 4), wrapped in the paginated envelope shape."""
    if not await check_db_connection():
        pytest.skip("No reachable database configured - skipping integration test")

    resp = await api_client.get("/api/v1/academic/boards?page=1&page_size=5&sort_by=name")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert {"page", "page_size", "total", "total_pages", "request_id"} <= body["meta"].keys()

    bad_sort_resp = await api_client.get("/api/v1/academic/boards?sort_by=not_a_real_column")
    assert bad_sort_resp.status_code == 422
    assert bad_sort_resp.json()["success"] is False
