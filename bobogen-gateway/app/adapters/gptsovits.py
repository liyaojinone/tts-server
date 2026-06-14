from app.adapters.base import BaseProviderAdapter, MappedRequest
from app.schemas.synthesize import UnifiedSynthesizeRequest


class GPTSoVITSAdapter(BaseProviderAdapter):
    provider_type = "gptsovits"

    def build_request(self, request: UnifiedSynthesizeRequest) -> MappedRequest:
        return MappedRequest(
            path="/tts",
            json={
                "text": request.text,
                "text_lang": request.language or "zh",
                "ref_audio_path": request.parameters.reference_audio,
                "prompt_text": request.parameters.reference_text or "",
                "prompt_lang": request.language or "zh",
                "media_type": request.output.format,
                "speed_factor": request.parameters.speed,
                **request.parameters.extra,
            },
        )
