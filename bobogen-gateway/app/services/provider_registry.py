from pathlib import Path

from app.adapters.cosyvoice import CosyVoiceAdapter
from app.adapters.f5tts import F5TTSAdapter
from app.adapters.gptsovits import GPTSoVITSAdapter
from app.adapters.indextts import IndexTTSAdapter
from app.adapters.stableaudio3 import StableAudio3Adapter
from app.adapters.voxcpm import VoxCPMAdapter
from app.config import PROVIDER_DIR, load_provider_configs
from app.core.exceptions import ModelNotFoundError, ProviderNotFoundError


class ProviderRegistry:
    def __init__(self, providers):
        self.providers = providers
        self.provider_map = {provider.provider_id: provider for provider in providers}
        self.model_map = {
            self.get_model_id(provider): provider
            for provider in providers
        }
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
            "stableaudio3": StableAudio3Adapter,
            "voxcpm": VoxCPMAdapter,
        }
        return mapping[provider_type]()

    def list_providers(self):
        return self.providers

    def get_model_id(self, provider):
        return provider.model_id or provider.provider_id

    def get_model_tasks(self, provider):
        if provider.tasks:
            return provider.tasks
        if provider.capabilities.synthesize:
            return ["tts.speech"]
        return []

    def list_models(self):
        return [
            (self.get_model_id(provider), provider, self.get_model_tasks(provider))
            for provider in self.providers
        ]

    def get_provider_by_model(self, model_id: str):
        provider = self.model_map.get(model_id)
        if provider is None:
            raise ModelNotFoundError(f"Model not found: {model_id}", {"model_id": model_id})
        return provider

    def get_provider(self, provider_id: str):
        provider = self.provider_map.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        return provider

    def get_adapter(self, provider_id: str):
        if provider_id not in self._adapters:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        return self._adapters[provider_id]
