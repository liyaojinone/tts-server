from fastapi.testclient import TestClient


def test_cosyvoice_app_exposes_protocol_routes():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    voices = client.get("/v1/voices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert voices.status_code == 200
    assert voices.json()["total"] >= 1


def test_cosyvoice_synthesize_test_mode_returns_audio():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "你好",
            "voice_id": "中文女",
            "language": "zh",
            "parameters": {"speed": 1.0},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")


def test_cosyvoice_clone_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("COSYVOICE_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "cosy-demo",
            "text": "参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    assert clone_response.json()["voice_id"] == "cosy-demo"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "cosy-demo" in voice_ids


def test_cosyvoice_synthesize_uses_cloned_voice_profile_when_reference_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("COSYVOICE_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "cosy-story",
            "text": "参考文本",
            "language": "zh",
            "emotion": "warm",
        },
    )
    assert clone_response.status_code == 200

    synth_response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接使用已注册的 CosyVoice 音色。",
            "voice_id": "cosy-story",
            "language": "zh",
            "parameters": {},
            "output": {"format": "wav"},
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["content-type"].startswith("audio/wav")
