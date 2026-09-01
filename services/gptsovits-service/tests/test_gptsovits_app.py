import asyncio
import builtins
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient
import pytest


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


def test_gptsovits_health_reports_versioned_model_id():
    from app.main import create_app

    client = TestClient(create_app(test_mode=True))
    health = client.get("/v1/health")

    assert health.status_code == 200
    assert health.json()["model"] == "GPT-SoVITS"
    assert health.json()["version"] == "gpt_sovits_v2pro"


def test_gptsovits_requires_explicit_versioned_weight_paths(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    (repo_dir / "GPT_SoVITS").mkdir(parents=True)
    model_dir = tmp_path / "gpt_sovits_v2pro"
    model_dir.mkdir()
    monkeypatch.setenv("GPTSOVITS_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("GPTSOVITS_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("GPTSOVITS_PRELOAD_ON_STARTUP", "true")
    monkeypatch.setenv("GPTSOVITS_GPT_WEIGHTS_PATH", str(model_dir / "s1v3.ckpt"))
    monkeypatch.setenv("GPTSOVITS_SOVITS_WEIGHTS_PATH", str(model_dir / "v2Pro" / "s2Gv2Pro.pth"))

    from app import handler as handler_module

    handler = handler_module.GPTSoVITSHandler()
    with pytest.raises(FileNotFoundError, match="gpt_sovits_v2pro"):
        asyncio.run(handler.startup())


def test_gptsovits_requires_explicit_v2pro_speaker_encoder(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    (repo_dir / "GPT_SoVITS").mkdir(parents=True)
    model_dir = tmp_path / "gpt_sovits_v2pro"
    (model_dir / "v2Pro").mkdir(parents=True)
    (model_dir / "s1v3.ckpt").write_bytes(b"test")
    (model_dir / "v2Pro" / "s2Gv2Pro.pth").write_bytes(b"test")
    (model_dir / "chinese-roberta-wwm-ext-large").mkdir()
    (model_dir / "chinese-hubert-base").mkdir()
    monkeypatch.setenv("GPTSOVITS_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("GPTSOVITS_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("GPTSOVITS_PRELOAD_ON_STARTUP", "true")
    monkeypatch.setenv("GPTSOVITS_GPT_WEIGHTS_PATH", str(model_dir / "s1v3.ckpt"))
    monkeypatch.setenv("GPTSOVITS_SOVITS_WEIGHTS_PATH", str(model_dir / "v2Pro" / "s2Gv2Pro.pth"))
    monkeypatch.setenv("GPTSOVITS_BERT_BASE_PATH", str(model_dir / "chinese-roberta-wwm-ext-large"))
    monkeypatch.setenv("GPTSOVITS_CNHUBERT_BASE_PATH", str(model_dir / "chinese-hubert-base"))
    monkeypatch.setenv(
        "GPTSOVITS_SV_WEIGHTS_PATH",
        str(model_dir / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt"),
    )

    from app import handler as handler_module

    with pytest.raises(FileNotFoundError, match="GPTSOVITS_SV_WEIGHTS_PATH"):
        asyncio.run(handler_module.GPTSoVITSHandler().startup())


def test_gptsovits_imports_upstream_from_repo_workdir_before_loading_models(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    (repo_dir / "GPT_SoVITS" / "eres2net").mkdir(parents=True)
    model_dir = tmp_path / "gpt_sovits_v2pro"
    (model_dir / "v2Pro").mkdir(parents=True)
    (model_dir / "sv").mkdir()
    (model_dir / "s1v3.ckpt").write_bytes(b"test")
    (model_dir / "v2Pro" / "s2Gv2Pro.pth").write_bytes(b"test")
    (model_dir / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt").write_bytes(b"test")
    (model_dir / "chinese-roberta-wwm-ext-large").mkdir()
    (model_dir / "chinese-hubert-base").mkdir()

    monkeypatch.setenv("GPTSOVITS_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("GPTSOVITS_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("GPTSOVITS_GPT_WEIGHTS_PATH", str(model_dir / "s1v3.ckpt"))
    monkeypatch.setenv("GPTSOVITS_SOVITS_WEIGHTS_PATH", str(model_dir / "v2Pro" / "s2Gv2Pro.pth"))
    monkeypatch.setenv("GPTSOVITS_BERT_BASE_PATH", str(model_dir / "chinese-roberta-wwm-ext-large"))
    monkeypatch.setenv("GPTSOVITS_CNHUBERT_BASE_PATH", str(model_dir / "chinese-hubert-base"))
    monkeypatch.setenv(
        "GPTSOVITS_SV_WEIGHTS_PATH",
        str(model_dir / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt"),
    )

    from app import handler as handler_module

    imported_from = []
    fake_tts_module = ModuleType("GPT_SoVITS.TTS_infer_pack.TTS")

    class FakeTTSConfig:
        def __init__(self, config):
            self.config = config
            self.configs_path = None

    class FakeTTS:
        def __init__(self, config):
            self.config = config

    fake_tts_module.TTS = FakeTTS
    fake_tts_module.TTS_Config = FakeTTSConfig
    fake_speaker_encoder = ModuleType("sv")
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "GPT_SoVITS.TTS_infer_pack.TTS":
            imported_from.append((name, Path.cwd()))
            return fake_tts_module
        if name == "sv":
            imported_from.append((name, Path.cwd()))
            return fake_speaker_encoder
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    original_cwd = Path.cwd()
    handler = handler_module.GPTSoVITSHandler()

    pipeline = handler._ensure_pipeline()

    assert isinstance(pipeline, FakeTTS)
    assert imported_from == [
        ("GPT_SoVITS.TTS_infer_pack.TTS", repo_dir),
        ("sv", repo_dir),
    ]
    assert fake_speaker_encoder.sv_path == str(model_dir / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt")
    assert Path.cwd() == original_cwd


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
            "voice_id": "shared-voice-001",
            "name": "narrator",
            "text": "这是参考文本",
            "language": "zh",
            "emotion": "calm",
        },
    )

    assert clone_response.status_code == 200
    clone_payload = clone_response.json()
    assert clone_payload["voice_id"] == "shared-voice-001"
    assert clone_payload["metadata"]["emotion"] == "calm"
    assert clone_payload["metadata"]["reference_text"] == "这是参考文本"

    voices_response = client.get("/v1/voices")
    assert voices_response.status_code == 200
    voice_ids = {voice["voice_id"] for voice in voices_response.json()["voices"]}
    assert "shared-voice-001" in voice_ids


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
