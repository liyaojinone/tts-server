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
