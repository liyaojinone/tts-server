import httpx

from app.adapters.base import BaseProviderAdapter
from app.schemas.generate import GenerateRequest
from app.services.audio_service import AudioResult


class StableAudio3Adapter(BaseProviderAdapter):
    provider_type = "stableaudio3"

    async def generate(self, provider, request: GenerateRequest) -> AudioResult:
        timeout = provider.runtime.request_timeout_ms / 1000
        async with httpx.AsyncClient(base_url=provider.network.base_url, timeout=timeout, trust_env=False) as client:
            response = await client.post("/v1/generate", json=request.model_dump(mode="json"))
            response.raise_for_status()
        return AudioResult(
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
            duration_seconds=float(response.headers["x-audio-duration"]) if "x-audio-duration" in response.headers else None,
            sample_rate=int(response.headers["x-sample-rate"]) if "x-sample-rate" in response.headers else None,
            format=request.output.format,
        )
