from fastapi.testclient import TestClient


def test_gptsovits_app_exposes_protocol_routes():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    voices = client.get("/v1/voices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert voices.status_code == 200
    assert voices.json()["total"] >= 1


def test_gptsovits_synthesize_test_mode_returns_audio():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "你好",
            "voice_id": "default",
            "language": "zh",
            "parameters": {
                "reference_audio": "E:/path/to/reference.wav",
                "reference_text": "庞白参考文本",
                "speed": 1.0,
            },
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")


def test_gptsovits_clone_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("GPTSOVITS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "narrator",
            "text": "这是参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    clone_payload = clone_response.json()
    assert clone_payload["voice_id"] == "narrator"
    assert clone_payload["metadata"]["emotion"] == "calm"
    assert clone_payload["metadata"]["reference_text"] == "这是参考文本"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "narrator" in voice_ids


def test_gptsovits_synthesize_uses_cloned_voice_profile_when_reference_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("GPTSOVITS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "story-voice",
            "text": "参考文本",
            "language": "zh",
            "emotion": "warm",
        },
    )

    assert clone_response.status_code == 200

    synth_response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接用已注册 voice_id 合成。",
            "voice_id": "story-voice",
            "language": "zh",
            "parameters": {},
            "output": {"format": "wav"},
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["content-type"].startswith("audio/wav")


def test_gptsovits_clone_status_returns_ready_for_existing_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("GPTSOVITS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={"name": "status-voice", "text": "参考文本", "language": "zh"},
    )
    assert clone_response.status_code == 200

    status_response = client.get("/v1/clone/status-voice/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready"
    assert status_response.json()["voice_id"] == "status-voice"
