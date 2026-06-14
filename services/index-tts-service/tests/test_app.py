from fastapi.testclient import TestClient


def test_indextts_app_exposes_protocol_routes():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    voices = client.get("/v1/voices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert voices.status_code == 200
    assert voices.json()["total"] >= 1


def test_indextts_clone_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEXTTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "index-demo",
            "text": "参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    assert clone_response.json()["voice_id"] == "index-demo"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "index-demo" in voice_ids


def test_indextts_synthesize_test_mode_returns_audio():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "你好",
            "voice_id": "index-default",
            "language": "zh",
            "parameters": {
                "reference_audio": r"E:/AiModel/bobogen-server/models/index-tts/repo/examples/voice_01.wav",
                "reference_text": "这是参考文本",
                "speed": 1.0,
            },
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")


def test_indextts_synthesize_uses_cloned_voice_profile_when_reference_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEXTTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "index-story",
            "text": "参考文本",
            "language": "zh",
            "emotion": "warm",
        },
    )
    assert clone_response.status_code == 200

    synth_response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接使用已注册的 IndexTTS 音色。",
            "voice_id": "index-story",
            "language": "zh",
            "parameters": {},
            "output": {"format": "wav"},
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["content-type"].startswith("audio/wav")


def test_indextts_synthesize_accepts_independent_emotion_reference_audio():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        data={
            "request": """{
                "text": "你好，这是独立情感参考测试。",
                "voice_id": "index-default",
                "language": "zh",
                "parameters": {
                    "reference_text": "主参考文本",
                    "extra": {
                        "emotion_reference_audio": "E:/AiModel/tts/emotion.wav"
                    }
                },
                "output": {"format": "wav"}
            }""",
        },
        files={
            "reference_audio": ("speaker.wav", b"RIFFspeaker", "audio/wav"),
            "emotion_reference_audio": ("emotion.wav", b"RIFFemotion", "audio/wav"),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-debug-reference-audio"].endswith(".wav")
    assert response.headers["x-debug-emotion-reference-audio"].endswith(".wav")


def test_indextts_startup_preloads_model_when_not_in_test_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("INDEXTTS_REPO_DIR", str(tmp_path / "repo"))
    monkeypatch.setenv("INDEXTTS_MODEL_DIR", str(tmp_path / "checkpoints"))
    (tmp_path / "repo").mkdir()
    (tmp_path / "checkpoints").mkdir()

    from app import handler as handler_module

    preload_calls = {"count": 0}

    def fake_ensure_tts(self):
        preload_calls["count"] += 1
        self.tts = object()
        self.ready = True
        self.last_error = None
        return self.tts

    monkeypatch.setattr(handler_module.IndexTTSHandler, "_ensure_tts", fake_ensure_tts)

    app = __import__("app.main", fromlist=["create_app"]).create_app(test_mode=False)

    with TestClient(app) as client:
        health = client.get("/v1/health")

    assert preload_calls["count"] == 1
    assert health.status_code == 200
    assert health.json()["ready"] is True
