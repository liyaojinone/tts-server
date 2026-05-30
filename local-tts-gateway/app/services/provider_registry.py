from pathlib import Path

from app.adapters.cosyvoice import CosyVoiceAdapter
from app.adapters.f5tts import F5TTSAdapter
from app.adapters.gptsovits import GPTSoVITSAdapter
from app.adapters.indextts import IndexTTSAdapter
from app.adapters.voxcpm import VoxCPMAdapter
from app.config import PROVIDER_DIR, load_provider_configs
from app.core.exceptions import ProviderNotFoundError


class ProviderRegistry:
    def __init__(self, providers):
        self.providers = providers
        self.provider_map = {provider.provider_id: provider for provider in providers}
        self._adapters = {
            provider.provider_id: self._create_adapter(provider.provider_type)
            for provider in providers
        }

    @classmethod
    def from_directory(cls, provider_dir: Path | None = None):
        return cls(load_provider_configs(provider_dir or PROVIDER_DIR))

    def _create_adapter(self, provider_type: str):
        mapping = {
            "cosyvoice": CosyVoiceAdapter,
            "f5-tts": F5TTSAdapter,
            "gptsovits": GPTSoVITSAdapter,
            "indextts": IndexTTSAdapter,
            "voxcpm": VoxCPMAdapter,
        }
        return mapping[provider_type]()

    def list_providers(self):
        return self.providers

    def get_provider(self, provider_id: str):
        provider = self.provider_map.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        return provider

    def get_adapter(self, provider_id: str):
        if provider_id not in self._adapters:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        return self._adapters[provider_id]
