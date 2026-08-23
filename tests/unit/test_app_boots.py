"""Phase 1 exit-criteria test: app boots, health check works, and every
module router is registered and reachable."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integration.test_helpers import auth_header, super_admin_token


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_all_module_routers_registered(client):
    token = super_admin_token()
    headers = auth_header(token)
    modules = [
        "identity", "academic", "student", "teacher", "question_bank",
        "blueprint", "paper_generation", "exam_management", "evaluation",
        "learning_profile", "analytics", "recommendation", "reports",
        "storage",
    ]
    for module in modules:
        response = client.get(f"/api/v1/{module}/ping")
        assert response.status_code == 200, f"{module} router not reachable"
        body = response.json()
        assert body["success"] is True
        assert body["data"]["module"] == module
        assert "request_id" in body["meta"]

    # integration requires role-based auth
    response = client.get("/api/v1/integration/ping", headers=headers)
    assert response.status_code == 200, "integration router not reachable"
    body = response.json()
    assert body["success"] is True
    assert body["data"]["module"] == "integration"
