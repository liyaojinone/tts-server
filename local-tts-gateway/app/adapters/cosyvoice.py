from app.adapters.base import BaseProviderAdapter, MappedRequest
from app.schemas.synthesize import UnifiedSynthesizeRequest


class CosyVoiceAdapter(BaseProviderAdapter):
    provider_type = "cosyvoice"

    def build_request(self, request: UnifiedSynthesizeRequest) -> MappedRequest:
        return MappedRequest(
            path="/v1/audio/speech",
            json={
                "model": "tts-1",
                "input": request.text,
                "voice": request.voice_id,
                "response_format": request.output.format,
                "speed": request.parameters.speed,
            },
        )
