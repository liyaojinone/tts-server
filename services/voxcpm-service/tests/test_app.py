from fastapi.testclient import TestClient


def test_voxcpm_app_exposes_protocol_routes():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    voices = client.get("/v1/voices")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert voices.status_code == 200
    assert voices.json()["total"] >= 1


def test_voxcpm_clone_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXCPM_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "voxcpm-demo",
            "text": "参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    assert clone_response.json()["voice_id"] == "voxcpm-demo"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "voxcpm-demo" in voice_ids


def test_voxcpm_design_creates_reusable_voice_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXCPM_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    design_response = client.post(
        "/v1/design",
        json={
            "name": "warm-host",
            "parameters": {
                "instruction": "温柔、年轻、自然，适合播客旁白",
                "language": "zh",
                "emotion": "warm",
            },
        },
    )

    assert design_response.status_code == 200
    assert design_response.json()["voice_id"] == "warm-host"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_payload = {voice["voice_id"]: voice for voice in voices_response.json()["voices"]}
    assert "warm-host" in voice_payload
    assert "design" in voice_payload["warm-host"]["tags"]


def test_voxcpm_synthesize_test_mode_supports_instruction_only_voice_design():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "你好，这是 VoxCPM2 音色设计测试。",
            "voice_id": "voxcpm2-default",
            "language": "zh",
            "parameters": {
                "instruction": "年轻女声，轻快，带一点笑意",
                "extra": {"cfg_value": 2.5, "inference_timesteps": 12},
            },
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-debug-mode"] == "design"
    assert response.headers["x-debug-instruction-length"] == str(len("年轻女声，轻快，带一点笑意"))


def test_voxcpm_synthesize_uses_cloned_voice_profile_when_reference_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXCPM_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    clone_response = client.post(
        "/v1/clone",
        files={"audio": ("ref.wav", b"RIFFdemo", "audio/wav")},
        data={
            "name": "story-voice",
            "text": "这是克隆参考文本",
            "language": "zh",
            "emotion": "warm",
        },
    )
    assert clone_response.status_code == 200

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接复用克隆音色。",
            "voice_id": "story-voice",
            "language": "zh",
            "parameters": {
                "instruction": "保持温暖和叙述感",
            },
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["x-debug-mode"] == "clone"
    assert response.headers["x-debug-reference-audio"].endswith("reference.wav")
    assert response.headers["x-debug-prompt-text-source"] == "profile"


def test_voxcpm_synthesize_uses_designed_voice_profile_when_instruction_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXCPM_PROFILE_DIR", str(tmp_path))

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    design_response = client.post(
        "/v1/design",
        json={
            "name": "calm-host",
            "parameters": {
                "instruction": "成熟男声，沉稳，适合新闻播报",
                "language": "zh",
            },
        },
    )
    assert design_response.status_code == 200

    response = client.post(
        "/v1/synthesize",
        json={
            "text": "直接使用已设计好的音色。",
            "voice_id": "calm-host",
            "language": "zh",
            "parameters": {},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["x-debug-mode"] == "design"
    assert response.headers["x-debug-instruction-length"] == str(len("成熟男声，沉稳，适合新闻播报"))
    assert response.headers["x-debug-instruction-source"] == "profile"


def test_voxcpm_startup_preloads_model_when_not_in_test_mode(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    model_dir = tmp_path / "model"
    repo_dir.mkdir()
    model_dir.mkdir()

    monkeypatch.setenv("VOXCPM_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("VOXCPM_MODEL_DIR", str(model_dir))

    from app import handler as handler_module

    preload_calls = {"count": 0}

    def fake_ensure_model(self):
        preload_calls["count"] += 1
        self.model = object()
        self.ready = True
        self.last_error = None
        return self.model

    monkeypatch.setattr(handler_module.VoxCPMHandler, "_ensure_model", fake_ensure_model)

    app = __import__("app.main", fromlist=["create_app"]).create_app(test_mode=False)

    with TestClient(app) as client:
        health = client.get("/v1/health")

    assert preload_calls["count"] == 1
    assert health.status_code == 200
    assert health.json()["ready"] is True
