from pydantic import BaseModel, Field


class SynthesizeParameters(BaseModel):
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: str | None = None
    emotion_intensity: float | None = None
    instruction: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    extra: dict = Field(default_factory=dict)


class OutputOptions(BaseModel):
    format: str = "wav"
    sample_rate: int | None = None


class UnifiedSynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    language: str | None = None
    parameters: SynthesizeParameters = Field(default_factory=SynthesizeParameters)
    output: OutputOptions = Field(default_factory=OutputOptions)


class ProviderSynthesizeRequest(UnifiedSynthesizeRequest):
    provider_id: str
