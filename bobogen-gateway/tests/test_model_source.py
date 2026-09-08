import asyncio
import os

from app.services.model_source import (
    ModelSourceConfig,
    ModelSourceConfigError,
    ModelSourceConfigStore,
)


def test_source_config_is_disabled_by_default_and_persists_atomically(tmp_path):
    config_path = tmp_path / "runtime" / "model-source-config.json"
    store = ModelSourceConfigStore(config_path)

    assert store.get() == ModelSourceConfig()
    assert store.get().env_for("qwen3_asr_0_6b") == {}

    configured = store.update(
        {
            "enabled": True,
            "hf_endpoint": "https://hf-mirror.com/",
            "modelscope_domain": "https://www.modelscope.cn/",
        }
    )

    assert configured.to_dict() == {
        "enabled": True,
        "hf_endpoint": "https://hf-mirror.com",
        "modelscope_domain": "www.modelscope.cn",
    }
    assert config_path.exists()
    assert store.get().env_for("qwen3_asr_0_6b") == {
        "HF_ENDPOINT": "https://hf-mirror.com",
        "QWEN3_ASR_HF_ENDPOINT": "https://hf-mirror.com",
    }
    assert store.get().env_for("campplus_speaker_diarization") == {
        "MODELSCOPE_DOMAIN": "www.modelscope.cn",
    }

    reloaded = ModelSourceConfigStore(config_path)
    assert reloaded.get() == configured

    disabled = reloaded.update({"enabled": False})
    assert disabled.env_for("qwen3_asr_0_6b") == {}


def test_source_config_rejects_enabled_without_an_endpoint(tmp_path):
    store = ModelSourceConfigStore(tmp_path / "source.json")

    try:
        store.update({"enabled": True})
    except ModelSourceConfigError as exc:
        assert "至少需要配置" in str(exc)
    else:
        raise AssertionError("expected source configuration validation to fail")


def test_model_source_config_does_not_change_existing_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "https://existing.example.com")
    store = ModelSourceConfigStore(tmp_path / "source.json")
    store.update({"enabled": True, "hf_endpoint": "https://hf-mirror.com"})

    assert os.environ["HF_ENDPOINT"] == "https://existing.example.com"


def test_process_scoped_model_source_env_is_applied_when_launching(tmp_path, monkeypatch):
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig
    import app.services.process_manager as process_manager_module
    from app.services.process_manager import ProcessManager

    provider = ProviderConfig(
        provider_id="source-provider",
        model_id="qwen3_asr_0_6b",
        provider_type="qwen3-asr",
        display_name="Source Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir=str(tmp_path),
            cwd=str(tmp_path),
            command=["python", "service.py"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5110,
            base_url="http://127.0.0.1:5110",
            healthcheck_path="/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )
    store = ModelSourceConfigStore(tmp_path / "source.json")
    store.update({"enabled": True, "hf_endpoint": "https://hf-mirror.com"})
    popen_args = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, cwd, env, stdout, stderr):
        popen_args.update({"env": env})
        return FakeProcess()

    monkeypatch.setattr(process_manager_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(process_manager_module.subprocess, "Popen", fake_popen)

    manager = ProcessManager({provider.provider_id: provider}, source_config_store=store)
    assert asyncio.run(manager._launch_process(provider)) == 4321
    assert popen_args["env"]["HF_ENDPOINT"] == "https://hf-mirror.com"
    assert popen_args["env"]["QWEN3_ASR_HF_ENDPOINT"] == "https://hf-mirror.com"
