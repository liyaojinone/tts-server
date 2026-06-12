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
        "local_voxcpm",
    }
    assert provider_types == {"cosyvoice", "f5-tts", "gptsovits", "indextts", "voxcpm"}


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
