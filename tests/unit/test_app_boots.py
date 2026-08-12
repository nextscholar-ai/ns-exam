"""Phase 1 exit-criteria test: app boots, health check works, and every
module router is registered and reachable."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_all_module_routers_registered(client):
    modules = [
        "identity", "academic", "student", "teacher", "question_bank",
        "blueprint", "paper_generation", "exam_management", "evaluation",
        "learning_profile", "analytics", "recommendation", "reports",
        "storage", "integration",
    ]
    for module in modules:
        response = client.get(f"/api/v1/{module}/ping")
        assert response.status_code == 200, f"{module} router not reachable"
        # Phase 7: every /api/v1/* response is wrapped in the standard envelope.
        body = response.json()
        assert body["success"] is True
        assert body["data"]["module"] == module
        assert "request_id" in body["meta"]
