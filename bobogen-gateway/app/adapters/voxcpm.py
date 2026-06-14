from app.adapters.base import BaseProviderAdapter, MappedRequest
from app.schemas.synthesize import UnifiedSynthesizeRequest


class VoxCPMAdapter(BaseProviderAdapter):
    provider_type = "voxcpm"

    def build_request(self, request: UnifiedSynthesizeRequest) -> MappedRequest:
        return MappedRequest(
            path="/v1/synthesize",
            json={
                "text": request.text,
                "voice_id": request.voice_id,
                "language": request.language,
                "parameters": {
                    "speed": request.parameters.speed,
                    "pitch": request.parameters.pitch,
                    "volume": request.parameters.volume,
                    "emotion": request.parameters.emotion,
                    "emotion_intensity": request.parameters.emotion_intensity,
                    "instruction": request.parameters.instruction,
                    "reference_audio": request.parameters.reference_audio,
                    "reference_text": request.parameters.reference_text,
                    "extra": request.parameters.extra,
                },
                "output": {
                    "format": request.output.format,
                    "sample_rate": request.output.sample_rate,
                },
            },
        )
