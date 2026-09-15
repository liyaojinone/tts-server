import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import REPO_ROOT
from app.routers.management import MODEL_CATALOG, _detect_model
from app.services.model_installer import (
    MODEL_INSTALL_PLANS,
    ModelInstallError,
    ModelInstaller,
    ModelInstallManager,
)


def test_qwen3_install_plan_has_no_weight_download_resources():
    plan = MODEL_INSTALL_PLANS["qwen3_asr_0_6b"]
    assert plan["source"]["url"] == "https://github.com/QwenLM/Qwen3-ASR.git"
    assert plan["source"]["revision"] == "7c6daf77a2421100f5fb066495372c00129d39ff"
    assert plan["resources"] == []
    assert "environment" in plan
    assert plan["environment"]["venv_dir"] == "services/qwen3-asr-service/.venv"
    assert plan["runtime"]["hf_repo_id"] == "Qwen/Qwen3-ASR-0.6B"

    large_plan = MODEL_INSTALL_PLANS["qwen3_asr_1_7b"]
    assert large_plan["resources"] == []
    assert large_plan["environment"]["venv_dir"] == "services/qwen3-asr-service/.venv"
    assert large_plan["runtime"]["hf_repo_id"] == "Qwen/Qwen3-ASR-1.7B"

    aligner_plan = MODEL_INSTALL_PLANS["qwen3_forced_aligner_0_6b"]
    assert aligner_plan["source"]["url"] == "https://github.com/QwenLM/Qwen3-ASR.git"
    assert aligner_plan["resources"] == []
    assert aligner_plan["environment"]["venv_dir"] == "services/qwen3-asr-service/.venv-aligner"
    assert [
        "git+https://github.com/huggingface/transformers"
    ] == [command[-1] for command in aligner_plan["environment"]["setup_commands"] if command[-1].startswith("git+")]
    assert aligner_plan["runtime"]["hf_repo_id"] == "Qwen/Qwen3-ForcedAligner-0.6B-hf"

    f5_plan = MODEL_INSTALL_PLANS["f5_tts"]
    assert f5_plan["source"]["url"] == "https://github.com/SWivid/F5-TTS.git"
    assert f5_plan["resources"] == []
    assert f5_plan["environment"]["venv_dir"] == "services/f5tts-service/.venv"
    assert f5_plan["runtime"]["hf_repo_id"] == "SWivid/F5-TTS"


def test_f5tts_install_plan_avoids_heavy_training_packages():
    plan = MODEL_INSTALL_PLANS["f5_tts"]
    commands = plan["environment"]["setup_commands"]
    joined = " ".join(" ".join(command) for command in commands)
    # 本体用 --no-deps 安装，避免拉入 gradio/torchcodec/bitsandbytes 等训练/CLI 包
    assert "models/f5-tts/repo" in joined and "--no-deps" in joined
    assert "gradio" not in joined
    assert "torchcodec" not in joined
    assert "bitsandbytes" not in joined
    # 运行期依赖要装上
    for dependency in ("transformers", "vocos", "torchdiffeq", "x_transformers", "cached_path"):
        assert dependency in joined
    assert plan["installation_marker"].endswith("f5_tts.json")


def test_voxcpm_install_plan_avoids_heavy_packages():
    plan = MODEL_INSTALL_PLANS["voxcpm2"]
    commands = plan["environment"]["setup_commands"]
    joined = " ".join(" ".join(command) for command in commands)
    assert "models/voxcpm/repo" in joined and "--no-deps" in joined
    assert "gradio" not in joined
    assert "torchcodec" not in joined
    assert "funasr" not in joined
    for dependency in ("transformers", "einops", "inflect", "wetext", "modelscope"):
        assert dependency in joined
    assert plan["installation_marker"].endswith("voxcpm2.json")


def test_stable_audio_install_plans_provision_environment_and_receipts():
    expected = {
        "stable_audio_3_small_sfx": (
            "stabilityai/stable-audio-3-small-sfx",
            "ae12755283df9d62ca39a9b050a39a0b607b8c20",
        ),
        "stable_audio_3_small_music": (
            "stabilityai/stable-audio-3-small-music",
            "0fef1392cd842149a2b6d445e181c97608faac06",
        ),
        "stable_audio_3_medium": (
            "stabilityai/stable-audio-3-medium",
            "27b5a21b791b1b033d193a9e1e3ce78493f102f9",
        ),
    }
    for model_id, (repo_id, revision) in expected.items():
        plan = MODEL_INSTALL_PLANS[model_id]
        assert plan["environment"]["venv_dir"] == "services/stable-audio3-service/.venv"
        assert plan["installation_marker"] == f"runtime/model-install-state/{model_id}.json"

        weights = [resource for resource in plan["resources"] if resource["kind"] == "hf_snapshot_cache"]
        assert len(weights) == 1
        assert weights[0]["repo_id"] == repo_id
        assert weights[0]["revision"] == revision
        assert weights[0]["cache_dir"] == "models/stable-audio-3/hf-home/hub"

        commands = " ".join(" ".join(command) for command in plan["environment"]["setup_commands"])
        assert "models/stable-audio-3/repo" in commands
        assert "services/stable-audio3-service" in commands
        assert "torch==2.7.1" in commands
        assert "download.pytorch.org/whl/cu128" in commands
        # ui/lora 是官方可选组（gradio/pytorch_lightning），不应进入安装清单
        assert "gradio" not in commands


def test_gated_model_download_failure_mentions_license_and_token(tmp_path, monkeypatch):
    installer = ModelInstaller(tmp_path)
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(
        installer, "_ensure_environment", lambda env_config, progress: tmp_path / "python.exe"
    )
    monkeypatch.setattr(installer, "_install_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer, "_write_installation_marker", lambda *args, **kwargs: None)

    def failing_download(resource, progress):
        raise ModelInstallError("401 Client Error: Unauthorized")

    monkeypatch.setattr(installer, "_download_resource", failing_download)

    with pytest.raises(ModelInstallError) as excinfo:
        installer.run(
            {"id": "stable_audio_3_small_sfx", "required_paths": []},
            "download",
            lambda event: None,
        )

    message = str(excinfo.value)
    assert "gated" in message
    assert "Token" in message


def test_indextts_install_plan_provisions_environment_and_runtime_weights():
    plan = MODEL_INSTALL_PLANS["index_tts_2"]
    assert plan["environment"]["venv_dir"] == "services/index-tts-service/.venv"
    assert plan["installation_marker"].endswith("runtime/model-install-state/index_tts_2.json")

    commands = " ".join(" ".join(command) for command in plan["environment"]["setup_commands"])
    assert "models/index-tts/repo" in commands
    assert "bobogen-protocol" in commands
    assert "bobogen-service-kit" in commands
    assert "services/index-tts-service" in commands
    assert "download.pytorch.org/whl/cu128" in commands
    assert "deepspeed" not in commands

    main = next(
        resource
        for resource in plan["resources"]
        if resource.get("repo_id") == "IndexTeam/IndexTTS-2"
    )
    assert main["kind"] == "hf_snapshot_local"
    assert main["target"] == "models/index-tts/checkpoints"

    # 官方运行时另外下载的附属权重必须预置到项目内缓存
    cached = {
        resource["repo_id"]: resource
        for resource in plan["resources"]
        if resource["kind"] == "hf_snapshot_cache"
    }
    assert set(cached) == {
        "facebook/w2v-bert-2.0",
        "amphion/MaskGCT",
        "funasr/campplus",
        "nvidia/bigvgan_v2_22khz_80band_256x",
    }
    assert {resource["cache_dir"] for resource in cached.values()} == {
        "models/index-tts/hf-home/hub"
    }
    assert cached["amphion/MaskGCT"]["allow_patterns"] == ["semantic_codec/*"]
    # 附属权重同样锁定 revision，保证可重复安装
    assert all(isinstance(resource.get("revision"), str) for resource in cached.values())


def test_hf_snapshot_cache_forwards_allow_patterns(tmp_path, monkeypatch):
    installer = ModelInstaller(tmp_path)
    captured: dict[str, object] = {}

    def snapshot_download(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(installer, "_hf_module", lambda: (None, snapshot_download))

    installer._download_hf_snapshot_cache(
        {
            "kind": "hf_snapshot_cache",
            "repo_id": "amphion/MaskGCT",
            "cache_dir": "models/index-tts/hf-home/hub",
            "allow_patterns": ["semantic_codec/*"],
        },
        lambda event: None,
    )

    assert captured["repo_id"] == "amphion/MaskGCT"
    assert captured["allow_patterns"] == ["semantic_codec/*"]
    assert str(captured["cache_dir"]).endswith("models\\index-tts\\hf-home\\hub") or str(
        captured["cache_dir"]
    ).endswith("models/index-tts/hf-home/hub")


def test_campplus_install_plan_provisions_environment_and_pipeline_packages():
    plan = MODEL_INSTALL_PLANS["campplus_speaker_diarization"]
    assert plan["environment"]["venv_dir"] == "services/speaker-diarization-service/.venv"
    assert plan["installation_marker"].endswith(
        "runtime/model-install-state/campplus_speaker_diarization.json"
    )

    resources = plan["resources"]
    assert {resource["model_id"] for resource in resources} == {
        "iic/speech_campplus_speaker-diarization_common",
        "damo/speech_campplus_sv_zh-cn_16k-common",
        "damo/speech_campplus-transformer_scl_zh-cn_16k-common",
        "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    }
    assert {resource["cache_dir"] for resource in resources} == {
        "models/speaker-diarization/modelscope-cache"
    }
    commands = " ".join(" ".join(command) for command in plan["environment"]["setup_commands"])
    assert "services/speaker-diarization-service" in commands


def test_tiger_install_plan_provisions_environment_and_inference_dependencies():
    plan = MODEL_INSTALL_PLANS["tiger-dnr"]
    assert plan["environment"]["venv_dir"] == "services/tiger-dnr-service/.venv"
    assert plan["installation_marker"].endswith("runtime/model-install-state/tiger-dnr.json")
    commands = " ".join(" ".join(command) for command in plan["environment"]["setup_commands"])
    assert "services/tiger-dnr-service" in commands
    assert "pytorch-lightning" in commands
    # 官方 requirements 里的 triton 在 Windows 装不上，推理依赖必须显式列出
    assert "triton" not in commands
    assert "safetensors" in commands

    # ffmpeg 必须随目录自带，否则拷到没有系统 ffmpeg 的机器无法解码
    ffmpeg_resources = [
        resource for resource in plan["resources"] if resource["kind"] == "ffmpeg_shared_zip"
    ]
    assert len(ffmpeg_resources) == 1
    assert ffmpeg_resources[0]["target"] == "services/tiger-dnr-service/.venv/ffmpeg"


def test_modelscope_cache_download_uses_returned_snapshot_directory(tmp_path, monkeypatch):
    import sys
    import types

    from app.services.model_installer import ModelInstallError

    snapshot_dir = (
        tmp_path
        / "models/speaker-diarization/modelscope-cache/models"
        / "iic--speech_campplus_speaker-diarization_common"
        / "snapshots"
        / "master"
    )
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "config.yaml").write_text("model: CAMPPlus", encoding="utf-8")

    recorded = {}

    def snapshot_download(model_id, **kwargs):
        recorded["model_id"] = model_id
        recorded["kwargs"] = kwargs
        return str(snapshot_dir)

    monkeypatch.setitem(
        sys.modules, "modelscope", types.SimpleNamespace(snapshot_download=snapshot_download)
    )

    installer = ModelInstaller(tmp_path)
    installer._download_modelscope_cache(
        {
            "kind": "modelscope_cache",
            "model_id": "iic/speech_campplus_speaker-diarization_common",
            "revision": "master",
            "cache_dir": "models/speaker-diarization/modelscope-cache",
        },
        lambda event: None,
    )

    assert recorded["model_id"] == "iic/speech_campplus_speaker-diarization_common"
    assert recorded["kwargs"]["revision"] == "master"
    assert recorded["kwargs"]["cache_dir"].endswith("models\\speaker-diarization\\modelscope-cache") or (
        recorded["kwargs"]["cache_dir"].endswith("models/speaker-diarization/modelscope-cache")
    )

    empty_dir = tmp_path / "empty-snapshot"
    empty_dir.mkdir()
    monkeypatch.setitem(
        sys.modules,
        "modelscope",
        types.SimpleNamespace(snapshot_download=lambda model_id, **kwargs: str(empty_dir)),
    )
    with pytest.raises(ModelInstallError):
        installer._download_modelscope_cache(
            {
                "kind": "modelscope_cache",
                "model_id": "iic/speech_campplus_speaker-diarization_common",
                "revision": "master",
                "cache_dir": "models/speaker-diarization/modelscope-cache",
            },
            lambda event: None,
        )


def test_url_zip_extract_redownloads_corrupt_cache(tmp_path, monkeypatch):
    import io
    import zipfile as zipfile_module

    from app.services.model_installer import ModelInstaller

    installer = ModelInstaller(tmp_path)
    cache = tmp_path / "runtime/model-download-cache/nltk_data.zip"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"PK\x03\x04truncated")

    payload = io.BytesIO()
    with zipfile_module.ZipFile(payload, "w") as archive:
        archive.writestr("nltk_data/corpora/cmudict.zip", b"dict")
    data = payload.getvalue()

    class FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size: int = -1) -> bytes:
            chunk = self._body[:size] if size and size > 0 else self._body
            self._body = self._body[len(chunk):]
            return chunk

    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=120: FakeResponse(data))

    installer._download_url_zip_extract(
        {
            "url": "https://example.invalid/nltk_data.zip",
            "cache_path": "runtime/model-download-cache/nltk_data.zip",
            "target": "services/gptsovits-service/.venv",
            "marker": "nltk_data/corpora/cmudict.zip",
        },
        lambda event: None,
    )

    marker = tmp_path / "services/gptsovits-service/.venv/nltk_data/corpora/cmudict.zip"
    assert marker.is_file()


def test_gptsovits_install_plan_preinstalls_opencc_and_service():
    plan = MODEL_INSTALL_PLANS["gpt_sovits_v2pro"]
    commands = plan["environment"]["setup_commands"]
    joined = " ".join(" ".join(command) for command in commands)
    # 预装 opencc wheel，避免官方 requirements 的 --no-binary=opencc 在 Windows 上编译源码
    assert any(command[:5] == ["{python}", "-m", "pip", "install", "opencc"] for command in commands)
    assert "services/gptsovits-service" in joined
    assert plan["installation_marker"].endswith("gpt_sovits_v2pro.json")


def test_service_kit_declares_python_multipart():
    # service-kit 的 /v1/clone 使用 Form/File，缺少 python-multipart 会导致服务无法启动
    text = (REPO_ROOT / "bobogen-service-kit" / "pyproject.toml").read_text(encoding="utf-8")
    assert "python-multipart" in text


def test_service_packages_declare_explicit_discovery():
    service_pyprojects = sorted((REPO_ROOT / "services").glob("*/pyproject.toml"))
    assert service_pyprojects
    for pyproject in service_pyprojects:
        text = pyproject.read_text(encoding="utf-8")
        assert "[tool.setuptools.packages.find]" in text, pyproject


def test_cosyvoice_install_plan_provisions_service_environment():
    plan = MODEL_INSTALL_PLANS["cosyvoice2"]
    assert plan["environment"]["venv_dir"] == "services/cosyvoice-service/.venv"
    commands = plan["environment"]["setup_commands"]
    joined = " ".join(" ".join(command) for command in commands)
    assert "models/cosyvoice/repo/requirements.txt" in joined
    assert "services/cosyvoice-service" in joined
    # openai-whisper 需在隔离环境外构建并跳过依赖，避免缺 pkg_resources
    assert any(
        "openai-whisper==20231117" in command and "--no-build-isolation" in command
        for command in commands
    )
    assert plan["installation_marker"].endswith("cosyvoice2.json")


def test_installer_retries_dependencies_when_environment_is_incomplete(tmp_path, monkeypatch):
    from app.services.model_installer import ModelInstaller

    installer = ModelInstaller(tmp_path)
    venv_python = tmp_path / "services/cosyvoice-service/.venv/Scripts/python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"python")
    executed: list[list[str]] = []

    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(installer, "_ensure_environment", lambda env, progress: venv_python)
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda args, cwd, progress, env=None: executed.append(args),
    )
    monkeypatch.setattr(installer, "_download_resource", lambda resource, progress: None)

    installer.run({"id": "cosyvoice2", "required_paths": []}, "repair", lambda event: None)

    assert executed, "缺少完成记录时应重新执行依赖安装"
    assert (tmp_path / "runtime/model-install-state/cosyvoice2.json").is_file()


def test_repair_reruns_setup_even_when_receipt_exists(tmp_path, monkeypatch):
    from app.services.model_installer import ModelInstaller

    installer = ModelInstaller(tmp_path)
    venv_python = tmp_path / "services/cosyvoice-service/.venv/Scripts/python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"python")
    marker = tmp_path / "runtime/model-install-state/cosyvoice2.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    executed: list[list[str]] = []

    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(installer, "_ensure_environment", lambda env, progress: venv_python)
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda args, cwd, progress, env=None: executed.append(args),
    )
    monkeypatch.setattr(installer, "_download_resource", lambda resource, progress: None)

    installer.run({"id": "cosyvoice2", "required_paths": []}, "repair", lambda event: None)

    assert executed, "修复操作应强制重跑安装步骤，以补齐缺失的依赖"


def test_installer_early_returns_when_marker_already_present(tmp_path, monkeypatch):
    from app.services.model_installer import ModelInstaller

    installer = ModelInstaller(tmp_path)
    venv_python = tmp_path / "services/cosyvoice-service/.venv/Scripts/python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"python")
    marker = tmp_path / "runtime/model-install-state/cosyvoice2.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    executed: list[list[str]] = []

    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda args, cwd, progress, env=None: executed.append(args),
    )

    installer.run({"id": "cosyvoice2", "required_paths": []}, "download", lambda event: None)

    assert executed == [], "安装记录存在且资源就绪时应直接早退"


def test_gptsovits_install_plan_provisions_ffmpeg_inside_its_virtual_environment():
    plan = MODEL_INSTALL_PLANS["gpt_sovits_v2pro"]
    resource = next(resource for resource in plan["resources"] if resource["kind"] == "ffmpeg_shared_zip")

    assert resource["target"] == "services/gptsovits-service/.venv/ffmpeg"
    assert resource["url"] == "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/assets/561416198"
    assert resource["sha256"] == "0968af68d5b2009c62bf726d6a9530c234bd3e158102823a8e7ee7f799257460"
    assert resource["package_glob"] == "ffmpeg-*-win64-lgpl-shared"



def test_install_request_operates_only_on_selected_model(tmp_path, monkeypatch):
    recorded_steps = []
    executed_commands = []

    installer = ModelInstaller(tmp_path)
    monkeypatch.setattr(
        installer,
        "_ensure_source",
        lambda source, progress: recorded_steps.append(("source", source["url"])),
    )
    monkeypatch.setattr(
        installer,
        "_ensure_environment",
        lambda env_config, progress: tmp_path / "fake-python.exe",
    )
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda args, cwd, progress, env=None: executed_commands.append((args, env)),
    )

    fake_model = {
        "id": "qwen3_asr_0_6b",
        "required_paths": [],
    }

    events = []
    installer.run(fake_model, "download", lambda event: events.append(event))

    assert any(ev.step == "source" and ev.message == "下载官方仓库" for ev in events)
    assert any(ev.step == "environment" and ev.message == "准备 Python 环境" for ev in events)
    assert any(ev.step == "dependencies" and ev.message == "安装官方依赖" for ev in events)
    assert any(ev.step == "done" and ev.message == "安装完成" for ev in events)
    assert len(recorded_steps) == 1
    assert recorded_steps[0] == ("source", "https://github.com/QwenLM/Qwen3-ASR.git")
    marker = tmp_path / "runtime/model-install-state/qwen3_asr_0_6b.json"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").find('"model_id": "qwen3_asr_0_6b"') >= 0


def test_mirror_setting_is_process_scoped_and_does_not_mutate_persistent_environment(
    tmp_path, monkeypatch
):
    original_hf_endpoint = os.environ.get("HF_ENDPOINT")
    passed_env = {}

    installer = ModelInstaller(tmp_path)
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(
        installer,
        "_ensure_environment",
        lambda env_config, progress: tmp_path / "fake-python.exe",
    )

    def fake_run_command(args, cwd, progress, env=None):
        if env:
            passed_env.update(env)

    monkeypatch.setattr(installer, "_run_command", fake_run_command)

    fake_model = {
        "id": "qwen3_asr_0_6b",
        "required_paths": [],
    }

    installer.run(
        fake_model,
        "download",
        lambda event: None,
        mirror="https://custom-mirror.example.com",
    )

    assert passed_env.get("HF_ENDPOINT") == "https://custom-mirror.example.com"
    assert os.environ.get("HF_ENDPOINT") == original_hf_endpoint


def test_status_distinguishes_repository_readiness_from_runtime_weight_readiness(tmp_path):
    qwen_model = next(m for m in MODEL_CATALOG if m["id"] == "qwen3_asr_0_6b")

    detected_stopped = _detect_model(qwen_model, process_manager=None)
    assert detected_stopped["runtime_weight_policy"] == "upstream_managed"
    assert detected_stopped["runtime_state"] == "stopped"

    mock_manager = MagicMock()
    mock_process_loading = SimpleNamespace(
        is_running=True,
        health_status={"ready": False},
    )
    mock_manager.get_process.return_value = mock_process_loading
    detected_loading = _detect_model(qwen_model, process_manager=mock_manager)
    assert detected_loading["runtime_state"] == "loading_weights"
    assert "正在下载/加载权重" in detected_loading["runtime_message"]

    mock_process_ready = SimpleNamespace(
        is_running=True,
        health_status={"ready": True},
    )
    mock_manager.get_process.return_value = mock_process_ready
    detected_ready = _detect_model(qwen_model, process_manager=mock_manager)
    assert detected_ready["runtime_state"] == "ready"
    assert "权重已就绪" in detected_ready["runtime_message"]


def test_complete_repair_reuses_local_resources_without_downloading_again(tmp_path, monkeypatch):
    required_path = "models/tiger/TIGER-DnR/local.marker"
    target = tmp_path / required_path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already downloaded")

    marker_path = tmp_path / "runtime/model-install-state/tiger-dnr.json"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("{}", encoding="utf-8")

    venv_python = tmp_path / "services/tiger-dnr-service/.venv/Scripts/python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"python")

    installer = ModelInstaller(tmp_path)
    calls = []
    dependency_runs = []
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(installer, "_download_resource", lambda resource, progress: calls.append(resource))
    monkeypatch.setattr(
        installer,
        "_install_dependencies",
        lambda env_config, python_exe, progress, mirror=None: dependency_runs.append(mirror),
    )

    events = []
    installer.run(
        {"id": "tiger-dnr", "required_paths": [required_path]},
        "repair",
        events.append,
        mirror="https://new-mirror.example.com",
    )

    # 资源已完整：修复只重跑环境依赖（用于补齐运行期依赖），绝不再下载资源
    assert calls == []
    assert dependency_runs == ["https://new-mirror.example.com"]
    assert any(event.step == "done" for event in events)


def test_gated_stable_audio_download_passes_stored_token_to_huggingface(tmp_path, monkeypatch):
    installer = ModelInstaller(tmp_path)
    captured_kwargs = {}
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(
        installer, "_ensure_environment", lambda env_config, progress: tmp_path / "python.exe"
    )
    monkeypatch.setattr(installer, "_install_dependencies", lambda *args, **kwargs: None)

    def snapshot_download(**kwargs):
        captured_kwargs.update(kwargs)
        snapshot = (
            Path(kwargs["cache_dir"])
            / "models--stabilityai--stable-audio-3-small-sfx"
            / "snapshots"
            / "revision"
        )
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        installer,
        "_hf_module",
        lambda: (None, snapshot_download),
    )

    installer.run(
        {
            "id": "stable_audio_3_small_sfx",
            "required_paths": [
                "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-small-sfx/snapshots"
            ],
        },
        "download",
        lambda event: None,
        hf_token="hf_example_secret_1234",
    )

    assert captured_kwargs["repo_id"] == "stabilityai/stable-audio-3-small-sfx"
    assert captured_kwargs["token"] == "hf_example_secret_1234"


def _run_manager_job_with_loop(tmp_path, catalog, prefetch):
    import asyncio
    import threading
    import time

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    manager = ModelInstallManager(tmp_path, catalog, prefetch=prefetch)
    manager._installer.run = lambda *args, **kwargs: None  # type: ignore[assignment]
    try:
        job = manager.start(catalog[0]["id"], "download", main_loop=loop)
        deadline = time.monotonic() + 5
        final = job
        while time.monotonic() < deadline:
            final = manager.get(job["id"])
            if final["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
    finally:
        loop.call_soon_threadsafe(loop.stop)
    return final


def test_upstream_managed_install_job_prefetches_official_weights(tmp_path):
    prefetched: list[str] = []

    async def prefetch(model_id: str) -> None:
        prefetched.append(model_id)

    final = _run_manager_job_with_loop(
        tmp_path,
        [
            {
                "id": "qwen_test",
                "required_paths": ["models/qwen-test/repo"],
                "runtime_weight_policy": "upstream_managed",
            }
        ],
        prefetch,
    )

    assert final["state"] == "succeeded"
    assert prefetched == ["qwen_test"]
    assert any("正在预取官方权重" in line for line in final["logs"])
    weights_marker = tmp_path / "runtime/model-install-state/qwen_test.weights.json"
    assert weights_marker.is_file()
    assert '"weights_prefetched": true' in weights_marker.read_text(encoding="utf-8")


def test_platform_managed_install_job_does_not_prefetch_weights(tmp_path):
    prefetched: list[str] = []

    async def prefetch(model_id: str) -> None:
        prefetched.append(model_id)

    final = _run_manager_job_with_loop(
        tmp_path,
        [
            {
                "id": "platform_test",
                "required_paths": ["models/platform-test/repo"],
                "runtime_weight_policy": "platform_managed",
            }
        ],
        prefetch,
    )

    assert final["state"] == "succeeded"
    assert prefetched == []
