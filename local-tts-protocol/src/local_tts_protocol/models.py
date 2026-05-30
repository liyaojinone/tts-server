from typing import Optional

from pydantic import BaseModel, Field


class Voice(BaseModel):
    voice_id: str
    name: str
    language: list[str] = Field(default_factory=list)
    gender: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class VoicesResponse(BaseModel):
    voices: list[Voice]
    total: int
    page: int = 1
    page_size: int = 100


class SynthesizeParameters(BaseModel):
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: Optional[str] = None
    emotion_intensity: Optional[float] = None
    instruction: Optional[str] = None
    reference_audio: Optional[str] = None
    reference_text: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class OutputOptions(BaseModel):
    format: str = "wav"
    sample_rate: Optional[int] = None


class SynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    language: Optional[str] = None
    parameters: SynthesizeParameters = Field(default_factory=SynthesizeParameters)
    output: OutputOptions = Field(default_factory=OutputOptions)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class CloneRequest(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None
    emotion: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CloneResponse(BaseModel):
    voice_id: str
    status: str = "ready"
    name: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CloneStatusResponse(BaseModel):
    task_id: str
    status: str
    voice_id: Optional[str] = None
    name: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class DesignRequest(BaseModel):
    base_voice_id: Optional[str] = None
    name: Optional[str] = None
    parameters: dict = Field(default_factory=dict)


class DesignResponse(BaseModel):
    voice_id: str
    name: Optional[str] = None
    status: str = "ready"
    metadata: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    model: Optional[str] = None
    version: Optional[str] = None
