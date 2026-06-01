from fastapi.testclient import TestClient


def test_health_and_provider_routes():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    health_response = client.get("/v1/health")
    providers_response = client.get("/v1/providers")
    status_response = client.get("/internal/providers/status")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"

    assert providers_response.status_code == 200
    assert len(providers_response.json()["providers"]) == 5

    assert status_response.status_code == 200
    assert "providers" in status_response.json()


def test_voices_alias_route():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/local_f5_tts/v1/voices")

    assert response.status_code == 200
    assert response.json()["total"] == 1
