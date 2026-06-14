from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class FileInput(BaseModel):
    kind: Literal["upload", "path", "data_uri"]
    field: Optional[str] = None
    path: Optional[str] = None
    data: Optional[str] = None

    @model_validator(mode="after")
    def validate_kind_value(self):
        if self.kind == "upload" and not self.field:
            raise ValueError("upload file input requires field")
        if self.kind == "path" and not self.path:
            raise ValueError("path file input requires path")
        if self.kind == "data_uri" and not self.data:
            raise ValueError("data_uri file input requires data")
        return self


def _convert_file_inputs(value: Any) -> Any:
    if isinstance(value, FileInput):
        return value
    if isinstance(value, dict):
        if value.get("kind") in {"upload", "path", "data_uri"}:
            return FileInput.model_validate(value)
        return {key: _convert_file_inputs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_convert_file_inputs(item) for item in value]
    return value


class GenerateOutputOptions(BaseModel):
    format: str = "wav"
    sample_rate: Optional[int] = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    task: str
    input: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    output: GenerateOutputOptions = Field(default_factory=GenerateOutputOptions)

    @field_validator("input", "parameters", mode="before")
    @classmethod
    def convert_file_inputs(cls, value):
        return _convert_file_inputs(value or {})


class ModelInfo(BaseModel):
    id: str
    name: str
    provider_id: str
    tasks: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    enabled: bool = True
    voices: list[Voice] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class GenerateError(BaseModel):
    error: ErrorDetail
