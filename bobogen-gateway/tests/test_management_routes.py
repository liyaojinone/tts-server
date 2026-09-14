from fastapi.testclient import TestClient
import time


class _FakeTokenProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"encrypted:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        return ciphertext.removeprefix(b"encrypted:")[::-1]


def test_management_page_is_served_by_gateway():
    from app.main import create_app

    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "模型服务" in response.text
    assert "http://127.0.0.1:6006/" in response.text
    assert "model-list" in response.text
    assert "版本 / 规模" in response.text
    assert "官方来源" in response.text
    assert 'data-operation="download"' in response.text
    assert 'data-operation="repair"' in response.text
    assert "安装器将在下一阶段接入" not in response.text
    assert "Hugging Face 授权" in response.text
    assert "/api/model-credentials/huggingface" in response.text
    assert "https://huggingface.co/settings/tokens" in response.text


def test_management_catalog_contains_all_configured_local_models_and_repository_links():
    from app.main import create_app
    from app.config import load_provider_configs
    from app.routers.management import MODEL_CATALOG

    client = TestClient(create_app())

    response = client.get("/api/model-services/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"]["name"] == "模型服务"
    models = payload["models"]
    configured_ids = {provider.model_id or provider.provider_id for provider in load_provider_configs()}
    assert {model["id"] for model in MODEL_CATALOG} == configured_ids
    assert {model["id"] for model in models} == {
        "cosyvoice2",
        "f5_tts",
        "gpt_sovits_v2pro",
        "index_tts_2",
        "voxcpm2",
        "stable_audio_3_small_sfx",
        "stable_audio_3_small_music",
        "stable_audio_3_medium",
        "qwen3_asr_0_6b",
        "qwen3_asr_1_7b",
        "qwen3_forced_aligner_0_6b",
        "campplus_speaker_diarization",
        "tiger-dnr",
    }
    for model in models:
        assert model["official_repo"].startswith("https://")
        assert model["purpose"]
        assert model["task"]
        assert model["version"]
        assert model["weight_size"]
        assert model["disk_estimate"]
        assert model["resource_root"]
        assert isinstance(model["service_port"], int)
        assert isinstance(model["source_platforms"], list)
        assert model["source_support"] in {"full", "mixed", "partial", "conditional", "unknown"}

    assert next(model for model in models if model["id"] == "voxcpm2")["parameter_size"] == "2B"
    assert next(model for model in models if model["id"] == "stable_audio_3_small_sfx")["parameter_size"] == "0.6B"
    assert next(model for model in models if model["id"] == "stable_audio_3_medium")["parameter_size"] == "2B"
    assert next(model for model in models if model["id"] == "qwen3_asr_1_7b")["weight_size"] == "约 4.7 GB"
    assert next(model for model in models if model["id"] == "gpt_sovits_v2pro")["parameter_size"] == "133M + 77M"
    assert next(model for model in models if model["id"] == "campplus_speaker_diarization")["parameter_size"] == "7.2M"
    assert next(model for model in models if model["id"] == "tiger-dnr")["parameter_size"] == "4.22M"

    qwen = next(model for model in MODEL_CATALOG if model["id"] == "qwen3_asr_0_6b")
    assert qwen["resource_root"] == "models/qwen3-asr/repo"
    assert qwen["runtime_weight_policy"] == "upstream_managed"
    assert qwen["required_paths"] == [
        "models/qwen3-asr/repo",
    ]
    assert qwen["installation_environment"].endswith(
        "services/qwen3-asr-service/.venv/Scripts/python.exe"
    )
    assert qwen["installation_marker"].endswith(
        "runtime/model-install-state/qwen3_asr_0_6b.json"
    )

    aligner = next(model for model in MODEL_CATALOG if model["id"] == "qwen3_forced_aligner_0_6b")
    assert aligner["resource_root"] == "models/qwen3-asr/repo"
    assert aligner["runtime_weight_policy"] == "upstream_managed"
    assert aligner["required_paths"] == [
        "models/qwen3-asr/repo",
    ]
    assert aligner["installation_environment"].endswith(
        "services/qwen3-asr-service/.venv-aligner/Scripts/python.exe"
    )

    f5 = next(model for model in MODEL_CATALOG if model["id"] == "f5_tts")
    assert f5["resource_root"] == "models/f5-tts/repo"
    assert f5["runtime_weight_policy"] == "upstream_managed"
    assert f5["required_paths"] == [
        "models/f5-tts/repo",
    ]


def test_cosyvoice_catalog_requires_install_receipt():
    from app.routers.management import MODEL_CATALOG

    cosyvoice = next(model for model in MODEL_CATALOG if model["id"] == "cosyvoice2")
    assert cosyvoice["installation_environment"].endswith(
        "services/cosyvoice-service/.venv/Scripts/python.exe"
    )
    assert cosyvoice["installation_marker"].endswith(
        "runtime/model-install-state/cosyvoice2.json"
    )

    f5 = next(model for model in MODEL_CATALOG if model["id"] == "f5_tts")
    assert f5["installation_environment"].endswith(
        "services/f5tts-service/.venv/Scripts/python.exe"
    )
    assert f5["installation_marker"].endswith("runtime/model-install-state/f5_tts.json")


def test_qwen_shared_repository_does_not_mark_unselected_variants_as_installed(
    monkeypatch, tmp_path
):
    import app.routers.management as management
    from app.routers.management import _detect_model

    monkeypatch.setattr(management, "REPO_ROOT", tmp_path)
    installer_log = tmp_path / "model-installer.log"
    installer_log.write_text(
        "[2026-09-14T00:00:00+00:00] [qwen3_asr_0_6b] 模型资源已准备完成\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(management, "INSTALLER_LOG", installer_log)

    (tmp_path / "models/qwen3-asr/repo").mkdir(parents=True)
    (tmp_path / "models/qwen3-asr/repo/README.md").write_text("official source", encoding="utf-8")
    small_python = tmp_path / "services/qwen3-asr-service/.venv/Scripts/python.exe"
    small_python.parent.mkdir(parents=True)
    small_python.write_bytes(b"python")
    weights_dir = tmp_path / "runtime/model-install-state"
    weights_dir.mkdir(parents=True)
    (weights_dir / "qwen3_asr_0_6b.weights.json").write_text(
        '{"model_id": "qwen3_asr_0_6b", "weights_prefetched": true}',
        encoding="utf-8",
    )

    models = {model["id"]: model for model in management.MODEL_CATALOG}
    small = _detect_model(models["qwen3_asr_0_6b"])
    large = _detect_model(models["qwen3_asr_1_7b"])
    aligner = _detect_model(models["qwen3_forced_aligner_0_6b"])

    assert small["status"] == "ready"
    assert large["status"] != "ready"
    assert aligner["status"] != "ready"
    assert any("model-install-state/qwen3_asr_1_7b.json" in path for path in large["missing_paths"])
    assert any("qwen3_asr_1_7b.weights.json" in path for path in large["missing_paths"])
    assert any(
        "qwen3-asr-service/.venv-aligner/Scripts/python.exe" in path
        for path in aligner["missing_paths"]
    )

def test_model_source_config_route_defaults_to_off_and_updates_project_config(tmp_path):
    from app.main import create_app
    from app.services.model_source import ModelSourceConfigStore

    app = create_app()
    store = ModelSourceConfigStore(tmp_path / "model-source-config.json")
    app.state.model_source_config_store = store
    app.state.process_manager.source_config_store = store
    app.state.model_install_manager._source_config_store = store
    client = TestClient(app)

    initial = client.get("/api/model-source-config")
    assert initial.status_code == 200
    assert initial.json()["config"] == {
        "enabled": False,
        "hf_endpoint": None,
        "modelscope_domain": None,
    }

    updated = client.put(
        "/api/model-source-config",
        json={
            "enabled": True,
            "hf_endpoint": "https://hf-mirror.com/",
            "modelscope_domain": "www.modelscope.cn",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["config"]["hf_endpoint"] == "https://hf-mirror.com"
    assert updated.json()["config"]["enabled"] is True
    assert updated.json()["restart_required"] is True

    invalid = client.put(
        "/api/model-source-config",
        json={"enabled": True, "hf_endpoint": None, "modelscope_domain": None},
    )
    assert invalid.status_code == 400

    disabled = client.put("/api/model-source-config", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["config"]["enabled"] is False


def test_huggingface_credential_routes_only_expose_masked_token_metadata(tmp_path):
    from app.main import create_app
    from app.services.huggingface_token import HuggingFaceTokenStore

    app = create_app()
    app.state.huggingface_token_store = HuggingFaceTokenStore(
        tmp_path / "huggingface-token.bin", protector=_FakeTokenProtector()
    )
    client = TestClient(app)

    initial = client.get("/api/model-credentials/huggingface")
    assert initial.status_code == 200
    assert initial.json()["credential"] == {"configured": False, "token_suffix": None}

    token = "hf_example_secret_1234"
    saved = client.put("/api/model-credentials/huggingface", json={"token": token})
    assert saved.status_code == 200
    assert saved.json()["credential"] == {"configured": True, "token_suffix": "1234"}
    assert token not in saved.text

    fetched = client.get("/api/model-credentials/huggingface")
    assert fetched.status_code == 200
    assert fetched.json()["credential"] == {"configured": True, "token_suffix": "1234"}
    assert token not in fetched.text

    deleted = client.delete("/api/model-credentials/huggingface")
    assert deleted.status_code == 200
    assert deleted.json()["credential"] == {"configured": False, "token_suffix": None}


def test_gated_model_download_requires_saved_huggingface_token(tmp_path):
    from app.main import create_app
    from app.services.huggingface_token import HuggingFaceTokenStore

    app = create_app()
    app.state.huggingface_token_store = HuggingFaceTokenStore(
        tmp_path / "huggingface-token.bin", protector=_FakeTokenProtector()
    )
    app.state.model_install_manager._huggingface_token_store = app.state.huggingface_token_store
    client = TestClient(app)

    response = client.post("/api/model-services/stable_audio_3_small_sfx/download")

    assert response.status_code == 400
    assert "Hugging Face Token" in response.json()["detail"]




def test_management_status_exposes_detection_and_console_data():
    from app.main import create_app

    client = TestClient(create_app())

    status_response = client.get("/api/model-services/status")
    logs_response = client.get("/api/model-services/logs?lines=5")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["service"]["status"] in {"running", "ready"}
    assert status_payload["models"]
    for model in status_payload["models"]:
        assert model["status"] in {"ready", "partial", "missing"}
        assert isinstance(model["missing_paths"], list)

    assert logs_response.status_code == 200
    logs_payload = logs_response.json()
    assert logs_payload["lines"] == 5
    assert isinstance(logs_payload["content"], str)


def test_management_installation_logs_do_not_mix_gateway_request_logs(monkeypatch, tmp_path):
    import app.routers.management as management
    from app.main import create_app

    installer_log = tmp_path / "model-installer.log"
    gateway_log = tmp_path / "gateway.log"
    installer_log.write_text("[model] downloading weights\n", encoding="utf-8")
    gateway_log.write_text('INFO: GET /api/model-services/status 200 OK\n', encoding="utf-8")
    monkeypatch.setattr(management, "INSTALLER_LOG", installer_log)
    monkeypatch.setattr(management, "GATEWAY_LOG", gateway_log)
    client = TestClient(create_app())

    response = client.get("/api/model-services/logs?lines=5")

    assert response.status_code == 200
    assert response.json()["content"] == "[model] downloading weights"


def test_management_model_download_is_an_idempotent_background_job():
    from app.config import REPO_ROOT
    from app.main import create_app

    # 幂等早退要求存在完成记录，避免把半成品环境当成就绪
    marker = REPO_ROOT / "runtime/model-install-state/index_tts_2.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    created_marker = not marker.exists()
    marker.write_text("{}", encoding="utf-8")
    try:
        client = TestClient(create_app())

        response = client.post("/api/model-services/index_tts_2/download")

        assert response.status_code == 202
        job = response.json()["job"]
        assert job["model_id"] == "index_tts_2"
        assert job["operation"] == "download"

        deadline = time.monotonic() + 5
        final_job = job
        while time.monotonic() < deadline:
            final_job = client.get(f"/api/model-services/jobs/{job['id']}").json()["job"]
            if final_job["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)

        assert final_job["state"] == "succeeded"
        assert "无需重复下载" in "\n".join(final_job["logs"])
    finally:
        if created_marker:
            marker.unlink(missing_ok=True)


def test_management_model_actions_reject_unknown_models():
    from app.main import create_app

    client = TestClient(create_app())

    response = client.post("/api/model-services/not-a-model/repair")

    assert response.status_code == 404


def test_resource_detection_rejects_empty_files_and_directories(tmp_path):
    from app.services.model_installer import is_resource_path_ready

    empty_file = tmp_path / "empty.bin"
    empty_file.touch()
    empty_directory = tmp_path / "empty-directory"
    empty_directory.mkdir()
    metadata_only_directory = tmp_path / "metadata-only-directory"
    metadata_only_directory.mkdir()
    (metadata_only_directory / ".cache").mkdir()
    (metadata_only_directory / ".cache" / "partial.metadata").write_text("partial", encoding="utf-8")
    ready_file = tmp_path / "ready.bin"
    ready_file.write_bytes(b"weights")
    ready_directory = tmp_path / "ready-directory"
    ready_directory.mkdir()
    (ready_directory / "config.json").write_text("{}", encoding="utf-8")

    assert not is_resource_path_ready(tmp_path, "empty.bin")
    assert not is_resource_path_ready(tmp_path, "empty-directory")
    assert not is_resource_path_ready(tmp_path, "metadata-only-directory")
    assert is_resource_path_ready(tmp_path, "ready.bin")
    assert is_resource_path_ready(tmp_path, "ready-directory")


def test_model_installer_repair_refills_zero_length_manifest_file(tmp_path, monkeypatch):
    from app.services.model_installer import ModelInstaller

    required_path = "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/s1v3.ckpt"
    target = tmp_path / required_path
    target.parent.mkdir(parents=True)
    target.touch()
    installer = ModelInstaller(tmp_path)
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    calls = []

    def refill(resource, progress):
        calls.append(resource["kind"])
        target.write_bytes(b"weights")

    monkeypatch.setattr(installer, "_download_resource", refill)

    installer.run(
        {"id": "gpt_sovits_v2pro", "required_paths": [required_path]},
        "repair",
        lambda progress: None,
    )

    assert calls[0] == "hf_files"
    assert target.read_bytes() == b"weights"


def test_model_install_manifest_pins_huggingface_resources():
    from app.services.model_installer import MODEL_INSTALL_PLANS

    for plan in MODEL_INSTALL_PLANS.values():
        for resource in plan.get("resources", []):
            if resource["kind"].startswith(("hf_", "modelscope_")):
                revision = resource.get("revision")
                assert isinstance(revision, str)
                assert revision
                if resource["kind"].startswith("hf_"):
                    assert len(revision) == 40


def test_management_warmup_endpoint_rejects_unknown_models():
    from app.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/model-services/unknown_model_123/warmup")
    assert response.status_code == 404
    assert "未知模型服务" in response.json()["detail"]


def test_management_warmup_endpoint_triggers_provider_warmup(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    async def mock_ensure_started(model_id):
        return True

    monkeypatch.setattr(app.state.process_manager, "ensure_started", mock_ensure_started)

    class MockResponse:
        status_code = 200

        def json(self):
            return {"status": "ready", "model": "qwen3_asr_0_6b"}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    response = client.post("/api/model-services/qwen3_asr_0_6b/warmup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["model_id"] == "qwen3_asr_0_6b"


def test_management_warmup_endpoint_surfaces_provider_errors(monkeypatch):
    import httpx
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    async def mock_ensure_started(model_id):
        return True

    monkeypatch.setattr(app.state.process_manager, "ensure_started", mock_ensure_started)

    class MockResponse:
        status_code = 500

        def json(self):
            return {
                "error": {
                    "code": "WARMUP_FAILED",
                    "message": "The checkpoint architecture is not recognized",
                }
            }

        @property
        def text(self):
            return "warmup failed"

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            return MockResponse()

        async def get(self, url, **kwargs):
            raise AssertionError("provider errors must not fall back to a health-only success")

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    response = client.post("/api/model-services/qwen3_forced_aligner_0_6b/warmup")

    assert response.status_code == 500
    assert "architecture is not recognized" in response.json()["detail"]


def test_management_warmup_endpoint_surfaces_provider_connection_errors(monkeypatch):
    import httpx
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    async def mock_ensure_started(model_id):
        return True

    monkeypatch.setattr(app.state.process_manager, "ensure_started", mock_ensure_started)

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            raise httpx.ReadError("")

        async def get(self, url, **kwargs):
            raise AssertionError("connection errors must not be converted into health-only success")

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    response = client.post("/api/model-services/qwen3_asr_0_6b/warmup")

    assert response.status_code == 502
    assert "ReadError" in response.json()["detail"]
