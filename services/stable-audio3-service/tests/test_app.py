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


def test_stable_audio3_test_mode_logs_prompt_and_silent_audio(caplog):
    import logging

    from app.main import create_app

    caplog.set_level(logging.INFO, logger="stable_audio3.generate")

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        json={
            "model": "stable-audio-3-small-sfx",
            "task": "audio.generate",
            "input": {"prompt": "short cinematic whoosh impact"},
            "parameters": {"duration": 1, "seed": 1234},
            "output": {"format": "wav", "sample_rate": 44100},
        },
    )

    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "short cinematic whoosh impact" in messages
    assert "testMode" in messages
    assert "silent" in messages


def test_stable_audio3_rejects_non_finite_model_output():
    import numpy as np

    from app.handler import _encode_wav

    audio = np.full((1, 2, 100), np.nan, dtype=np.float32)

    try:
        _encode_wav(audio, 44100)
    except RuntimeError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("expected non-finite audio to be rejected")
