import pytest


def test_registry_returns_correct_adapter_for_provider_type():
    from app.services.provider_registry import ProviderRegistry

    registry = ProviderRegistry.from_directory()

    assert registry.get_adapter("cosyvoice2").provider_type == "cosyvoice"
    assert registry.get_adapter("f5_tts").provider_type == "f5-tts"
    assert registry.get_adapter("gpt_sovits_v2pro").provider_type == "gptsovits"
    assert registry.get_adapter("index_tts_2").provider_type == "indextts"
    assert registry.get_adapter("stable_audio_3_small_sfx").provider_type == "stableaudio3"
    assert registry.get_adapter("voxcpm2").provider_type == "voxcpm"


def test_registry_rejects_duplicate_model_id_instead_of_silently_overwriting():
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig
    from app.services.provider_registry import ProviderRegistry

    def provider(provider_id: str, model_id: str, port: int) -> ProviderConfig:
        return ProviderConfig(
            provider_id=provider_id,
            model_id=model_id,
            provider_type="f5-tts",
            display_name=provider_id,
            runtime=RuntimeConfig(root_dir="C:/service", cwd="C:/service", command=["python"]),
            network=NetworkConfig(
                host="127.0.0.1",
                port=port,
                base_url=f"http://127.0.0.1:{port}",
            ),
            capabilities=CapabilityConfig(),
        )

    with pytest.raises(ValueError, match="Duplicate model_id"):
        ProviderRegistry([provider("f5_tts_v1", "f5_tts", 5201), provider("f5_tts_v2", "f5_tts", 5202)])


def test_registry_keeps_multiple_versions_of_one_provider_type_separate():
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig
    from app.services.provider_registry import ProviderRegistry

    def provider(provider_id: str, model_id: str, port: int) -> ProviderConfig:
        return ProviderConfig(
            provider_id=provider_id,
            model_id=model_id,
            provider_type="gptsovits",
            display_name=provider_id,
            runtime=RuntimeConfig(root_dir="C:/service", cwd="C:/service", command=["python"]),
            network=NetworkConfig(
                host="127.0.0.1",
                port=port,
                base_url=f"http://127.0.0.1:{port}",
            ),
            capabilities=CapabilityConfig(),
        )

    registry = ProviderRegistry(
        [
            provider("gpt_sovits_v2pro", "gpt_sovits_v2pro", 5201),
            provider("gpt_sovits_v2pro_plus", "gpt_sovits_v2pro_plus", 5202),
        ]
    )

    assert registry.get_provider_by_model("gpt_sovits_v2pro").provider_id == "gpt_sovits_v2pro"
    assert registry.get_provider_by_model("gpt_sovits_v2pro_plus").provider_id == "gpt_sovits_v2pro_plus"
