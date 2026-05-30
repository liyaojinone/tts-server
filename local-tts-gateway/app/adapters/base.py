from dataclasses import dataclass, field

import httpx

from app.schemas.synthesize import UnifiedSynthesizeRequest
from app.schemas.voice import VoiceResponse, VoicesResponse
from app.services.audio_service import AudioResult


@dataclass
class MappedRequest:
    path: str
    method: str = "POST"
    json: dict = field(default_factory=dict)
    files: dict | None = None


class BaseProviderAdapter:
    provider_type = "base"

    def build_request(self, request: UnifiedSynthesizeRequest) -> MappedRequest:
        raise NotImplementedError

    async def list_voices(self, provider):
        voices = [
            VoiceResponse(
                voice_id=voice.voice_id,
                name=voice.name,
                language=voice.language,
                gender=voice.gender,
                description=voice.description,
                tags=voice.tags,
                metadata=voice.metadata,
            )
            for voice in provider.voices
        ]
        return VoicesResponse(voices=voices, total=len(voices))

    async def synthesize(self, provider, request: UnifiedSynthesizeRequest, files=None) -> AudioResult:
        mapped = self.build_request(request)
        if files:
            mapped.files = files
        timeout = provider.runtime.request_timeout_ms / 1000
        async with httpx.AsyncClient(base_url=provider.network.base_url, timeout=timeout, trust_env=False) as client:
            response = await client.request(mapped.method, mapped.path, json=mapped.json, files=mapped.files)
            response.raise_for_status()
        return AudioResult(
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
            duration_seconds=float(response.headers["x-audio-duration"]) if "x-audio-duration" in response.headers else None,
            sample_rate=int(response.headers["x-sample-rate"]) if "x-sample-rate" in response.headers else None,
        )

    async def healthcheck(self, provider) -> bool:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{provider.network.base_url}{provider.network.healthcheck_path}")
            return response.status_code == 200

    async def clone(self, provider, audio, text="", name="", language="zh", emotion=""):
        async with httpx.AsyncClient(base_url=provider.network.base_url, timeout=30.0, trust_env=False) as client:
            files = {"audio": (audio.filename, await audio.read(), audio.content_type or "audio/wav")}
            data = {"text": text, "name": name, "language": language, "emotion": emotion}
            response = await client.post("/v1/clone", files=files, data=data)
            response.raise_for_status()
        return response.json()
