from pathlib import Path


def test_load_provider_configs():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"

    providers = load_provider_configs(config_dir)

    provider_ids = {provider.provider_id for provider in providers}
    provider_types = {provider.provider_type for provider in providers}

    assert provider_ids == {
        "cosyvoice-default",
        "f5tts-default",
        "gptsovits-default",
        "indextts-default",
        "voxcpm-default",
    }
    assert provider_types == {"cosyvoice", "f5-tts", "gptsovits", "indextts", "voxcpm"}
