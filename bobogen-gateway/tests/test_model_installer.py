import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import REPO_ROOT
from app.routers.management import MODEL_CATALOG, _detect_model
from app.services.model_installer import (
    MODEL_INSTALL_PLANS,
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

    installer = ModelInstaller(tmp_path)
    calls = []
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)
    monkeypatch.setattr(installer, "_download_resource", lambda resource, progress: calls.append(resource))

    events = []
    installer.run(
        {"id": "tiger-dnr", "required_paths": [required_path]},
        "repair",
        events.append,
        mirror="https://new-mirror.example.com",
    )

    assert calls == []
    assert any(event.step == "verify" and "无需重复下载" in event.message for event in events)


def test_gated_stable_audio_download_passes_stored_token_to_huggingface(tmp_path, monkeypatch):
    installer = ModelInstaller(tmp_path)
    captured_kwargs = {}
    monkeypatch.setattr(installer, "_ensure_source", lambda source, progress: None)

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
