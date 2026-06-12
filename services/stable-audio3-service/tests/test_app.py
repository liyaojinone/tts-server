from fastapi.testclient import TestClient


def test_stable_audio3_service_health_and_test_mode_generation():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["model"] == "stable-audio-3-small-sfx"

    response = client.post(
        "/v1/generate",
        json={
            "model": "stable-audio-3-small-sfx",
            "task": "audio.generate",
            "input": {"prompt": "short cinematic whoosh impact"},
            "parameters": {"duration": 2, "seed": 1234},
            "output": {"format": "wav", "sample_rate": 44100},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-model-id"] == "stable-audio-3-small-sfx"
    assert response.headers["x-task"] == "audio.generate"
    assert response.content.startswith(b"RIFF")


def test_stable_audio3_service_rejects_unsupported_task():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        json={
            "model": "stable-audio-3-small-sfx",
            "task": "tts.speech",
            "input": {"text": "你好"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_TASK"
