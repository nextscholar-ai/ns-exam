"""Phase 7 §5.2/§5.3: response envelope and error format, using TestClient
against the already-registered /ping endpoints - no DB needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.test_helpers import auth_header, super_admin_token


def test_success_envelope_shape(client):
    response = client.get("/api/v1/identity/ping")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"module": "identity", "status": "ok"}
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]


def test_404_error_envelope_shape(client):
    token = super_admin_token()
    response = client.get(
        "/api/v1/jobs/does-not-exist",
        headers=auth_header(token),
    )
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "does-not-exist" in body["error"]["message"]
    assert "request_id" in body["meta"]


def test_health_endpoint_not_enveloped():
    """/health is outside /api/v1 and stays a plain body (Phase 7 envelope
    only applies under the API prefix)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        response = c.get("/health")
    assert response.json() == {"status": "ok"}
