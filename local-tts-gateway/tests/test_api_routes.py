from fastapi.testclient import TestClient


def test_health_and_provider_routes():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    health_response = client.get("/v1/health")
    providers_response = client.get("/v1/providers")
    status_response = client.get("/v1/providers/status")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"

    assert providers_response.status_code == 200
    providers = providers_response.json()["providers"]
    assert len(providers) == 6
    assert any(provider["provider_id"] == "stable_audio_3_small_sfx" for provider in providers)

    assert status_response.status_code == 200
    assert "providers" in status_response.json()


def test_voices_alias_route():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/local_f5_tts/v1/voices")

    assert response.status_code == 200
    assert response.json()["total"] == 1
