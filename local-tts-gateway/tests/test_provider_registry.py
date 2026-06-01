def test_registry_returns_correct_adapter_for_provider_type():
    from app.services.provider_registry import ProviderRegistry

    registry = ProviderRegistry.from_directory()

    assert registry.get_adapter("local_cosyvoice2").provider_type == "cosyvoice"
    assert registry.get_adapter("local_f5_tts").provider_type == "f5-tts"
    assert registry.get_adapter("local_gpt_sovits").provider_type == "gptsovits"
    assert registry.get_adapter("local_index_tts").provider_type == "indextts"
    assert registry.get_adapter("local_voxcpm").provider_type == "voxcpm"
