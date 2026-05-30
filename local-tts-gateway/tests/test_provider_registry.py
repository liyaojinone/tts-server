def test_registry_returns_correct_adapter_for_provider_type():
    from app.services.provider_registry import ProviderRegistry

    registry = ProviderRegistry.from_directory()

    assert registry.get_adapter("cosyvoice-default").provider_type == "cosyvoice"
    assert registry.get_adapter("f5tts-default").provider_type == "f5-tts"
    assert registry.get_adapter("gptsovits-default").provider_type == "gptsovits"
    assert registry.get_adapter("indextts-default").provider_type == "indextts"
    assert registry.get_adapter("voxcpm-default").provider_type == "voxcpm"
