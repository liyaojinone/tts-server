from fastapi.testclient import TestClient


def test_f5tts_app_exposes_protocol_routes():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    voices = client.get("/v1/voices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert voices.status_code == 200
    assert voices.json()["total"] >= 1


def test_f5tts_clone_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("F5TTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "f5-demo",
            "text": "参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    assert clone_response.json()["voice_id"] == "f5-demo"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "f5-demo" in voice_ids


def test_f5tts_synthesize_uses_cloned_voice_profile_when_reference_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("F5TTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "f5-story",
            "text": "参考文本",
            "language": "zh",
            "emotion": "warm",
        },
    )
    assert clone_response.status_code == 200

    synth_response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接使用已注册的 F5TTS 音色。",
            "voice_id": "f5-story",
            "language": "zh",
            "parameters": {},
            "output": {"format": "wav"},
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["content-type"].startswith("audio/wav")


def test_f5tts_synthesize_prefers_request_reference_over_cloned_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("F5TTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("profile-ref.wav", b"RIFFprofile", "audio/wav")},
        data={
            "name": "voice",
            "text": "profile 参考文本",
            "language": "zh",
            "emotion": "neutral",
        },
    )
    assert clone_response.status_code == 200

    synth_response = client.post(
        "/v1/synthesize",
        data={
            "request": """{
                "text": "合成文本。",
                "voice_id": "voice",
                "language": "zh",
                "parameters": {},
                "output": {"format": "wav"}
            }""",
            "reference_text": "上传参考文本",
        },
        files={
            "reference_audio": ("uploaded-ref.mp3", b"ID3uploaded", "audio/mpeg"),
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["x-debug-reference-audio"].endswith(".mp3")
    assert "voice\\reference.wav" not in synth_response.headers["x-debug-reference-audio"]
    assert synth_response.headers["x-debug-reference-text-source"] == "upload"
    assert synth_response.headers["x-debug-reference-text-length"] == str(len("上传参考文本"))


def test_f5tts_synthesize_preserves_uploaded_reference_audio_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("F5TTS_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    synth_response = client.post(
        "/v1/synthesize",
        data={
            "request": """{
                "text": "直接使用上传的参考音频。",
                "voice_id": "f5-default",
                "language": "zh",
                "parameters": {},
                "output": {"format": "wav"}
            }""",
            "reference_text": "这是参考文本",
        },
        files={
            "reference_audio": ("neutral_这是参考文本.mp3", b"ID3demo", "audio/mpeg"),
        },
    )

    assert synth_response.status_code == 200
    assert synth_response.headers["content-type"].startswith("audio/wav")
