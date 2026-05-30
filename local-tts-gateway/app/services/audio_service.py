from dataclasses import dataclass

from fastapi import Response


@dataclass
class AudioResult:
    content: bytes
    content_type: str
    duration_seconds: float | None = None
    sample_rate: int | None = None
    format: str | None = None


def build_audio_response(provider_id: str, audio: AudioResult) -> Response:
    headers = {"X-Provider-Id": provider_id}
    if audio.duration_seconds is not None:
        headers["X-Audio-Duration"] = str(audio.duration_seconds)
    if audio.sample_rate is not None:
        headers["X-Sample-Rate"] = str(audio.sample_rate)
    return Response(content=audio.content, media_type=audio.content_type, headers=headers)
