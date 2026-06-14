from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.voice import VoiceResponse


class FileInput(BaseModel):
    kind: Literal["upload", "path", "data_uri"]
    field: str | None = None
    path: str | None = None
    data: str | None = None

    @model_validator(mode="after")
    def validate_kind_value(self):
        if self.kind == "upload" and not self.field:
            raise ValueError("upload file input requires field")
        if self.kind == "path" and not self.path:
            raise ValueError("path file input requires path")
        if self.kind == "data_uri" and not self.data:
            raise ValueError("data_uri file input requires data")
        return self


def convert_file_inputs(value: Any) -> Any:
    if isinstance(value, FileInput):
        return value
    if isinstance(value, dict):
        if value.get("kind") in {"upload", "path", "data_uri"}:
            return FileInput.model_validate(value)
        return {key: convert_file_inputs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [convert_file_inputs(item) for item in value]
    return value


class GenerateOutputOptions(BaseModel):
    format: str = "wav"
    sample_rate: int | None = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    task: str
    input: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    output: GenerateOutputOptions = Field(default_factory=GenerateOutputOptions)

    @field_validator("input", "parameters", mode="before")
    @classmethod
    def normalize_file_inputs(cls, value):
        return convert_file_inputs(value or {})


class ModelInfo(BaseModel):
    id: str
    name: str
    provider_id: str
    tasks: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    enabled: bool = True
    voices: list[VoiceResponse] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
