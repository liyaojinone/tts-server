from pathlib import Path


def test_load_provider_configs():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"

    providers = load_provider_configs(config_dir)

    provider_ids = {provider.provider_id for provider in providers}
    provider_types = {provider.provider_type for provider in providers}

    assert provider_ids == {
        "local_cosyvoice2",
        "local_f5_tts",
        "local_gpt_sovits",
        "local_index_tts",
        "stable_audio_3_small_sfx",
        "local_voxcpm",
    }
    assert provider_types == {"cosyvoice", "f5-tts", "gptsovits", "indextts", "stableaudio3", "voxcpm"}
    assert {provider.runtime.launch_mode for provider in providers} == {"process"}


def test_target_providers_launch_repository_local_services():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"

    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    expected = {
        "local_cosyvoice2": ("cosyvoice-service", "COSYVOICE_REPO_DIR", r"models\cosyvoice\repo"),
        "local_f5_tts": ("f5tts-service", "F5TTS_REPO_DIR", r"models\f5-tts\repo"),
        "local_gpt_sovits": ("gptsovits-service", "GPTSOVITS_REPO_DIR", r"models\gpt-sovits\repo"),
    }
    for provider_id, (service_dir, repo_env, repo_suffix) in expected.items():
        provider = providers[provider_id]
        command = provider.runtime.command

        assert provider.runtime.root_dir.endswith(rf"services\{service_dir}")
        assert provider.runtime.cwd.endswith(rf"services\{service_dir}")
        assert command[:2] == ["powershell", "-File"]
        assert command[2].endswith(rf"services\{service_dir}\start.ps1")
        assert provider.runtime.env[repo_env].endswith(repo_suffix)
        assert provider.network.healthcheck_path == "/v1/health"
        assert provider.capabilities.clone is True


def test_stable_audio3_provider_launches_repository_local_service():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    provider = providers["stable_audio_3_small_sfx"]

    assert provider.model_id == "stable-audio-3-small-sfx"
    assert provider.provider_type == "stableaudio3"
    assert provider.tasks == ["audio.generate"]
    assert provider.runtime.root_dir.endswith(r"services\stable-audio3-service")
    assert provider.runtime.cwd.endswith(r"services\stable-audio3-service")
    assert provider.runtime.command[:2] == ["powershell", "-File"]
    assert provider.runtime.command[2].endswith(r"services\stable-audio3-service\start.ps1")
    assert provider.runtime.env["STABLE_AUDIO3_REPO_DIR"].endswith(r"models\stable-audio-3\repo")
    assert provider.network.healthcheck_path == "/v1/health"
    assert provider.capabilities.synthesize is False


def test_docker_deployment_loads_only_docker_provider_configs(monkeypatch):
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    monkeypatch.setenv("BOBOGEN_DEPLOYMENT", "docker")

    providers = load_provider_configs(config_dir)

    assert [provider.provider_id for provider in providers] == ["stable_audio_3_small_sfx"]
    provider = providers[0]
    assert provider.runtime.launch_mode == "external"
    assert provider.network.base_url == "http://stable-audio3:5106"
    assert provider.model_id == "stable-audio-3-small-sfx"
    assert provider.tasks == ["audio.generate"]


def test_linux_deployment_loads_stable_audio3_linux_provider(monkeypatch):
    import app.config as config

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    monkeypatch.delenv("BOBOGEN_DEPLOYMENT", raising=False)
    monkeypatch.setattr(config, "_IS_LINUX", True)
    monkeypatch.setattr(config, "_IS_WIN", False)

    providers = {provider.provider_id: provider for provider in config.load_provider_configs(config_dir)}
    provider = providers["stable_audio_3_small_sfx"]

    assert provider.runtime.launch_mode == "process"
    assert provider.runtime.command[0] == "bash"
    assert provider.runtime.command[1].replace("\\", "/").endswith("/services/stable-audio3-service/start.sh")
    assert provider.runtime.env["STABLE_AUDIO3_REPO_DIR"].replace("\\", "/").endswith("/models/stable-audio-3/repo")
