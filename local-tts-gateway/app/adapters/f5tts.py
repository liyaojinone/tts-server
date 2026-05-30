from app.adapters.base import BaseProviderAdapter, MappedRequest
from app.schemas.synthesize import UnifiedSynthesizeRequest


class F5TTSAdapter(BaseProviderAdapter):
    provider_type = "f5-tts"

    def build_request(self, request: UnifiedSynthesizeRequest) -> MappedRequest:
        payload = {
            "ref_audio": request.parameters.reference_audio,
            "text": request.text,
            "ref_text": request.parameters.reference_text or "",
            "speed": request.parameters.speed,
        }
        payload.update(request.parameters.extra)
        return MappedRequest(path="/tts", json=payload)
