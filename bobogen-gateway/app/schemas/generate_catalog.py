from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.generate import FileInput, GenerateOutputOptions, GenerateRequest, convert_file_inputs


class DynamicInputModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DynamicParametersModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class StableAudio3Input(DynamicInputModel):
    prompt: str = Field(..., description="音效或音乐片段的文本描述。")


class StableAudio3Parameters(DynamicParametersModel):
    negative_prompt: str | None = Field(default=None, description="不希望生成的声音特征。")
    duration: float = Field(default=7, description="生成音频时长，单位秒。")
    steps: int = Field(default=8, description="推理步数。")
    cfg_scale: float = Field(default=1.0, description="提示词引导强度。")
    seed: int = Field(default=-1, description="-1 为随机；固定种子可复现结果。")
    batch_size: int = Field(default=1, description="批量大小；本地/云端单卡建议保持 1。")
    truncate_output_to_duration: bool = Field(default=True, description="是否将输出裁切到指定时长。")


class TTSInput(DynamicInputModel):
    text: str = Field(..., description="需要合成的文本。")
    voice: str | None = Field(default=None, description="统一生成接口使用的音色 ID。")
    voice_id: str | None = Field(default=None, description="兼容旧接口命名的音色 ID。")
    language: str | None = Field(default="zh", description="语言代码。")


class TTSParameters(DynamicParametersModel):
    reference_audio: FileInput | str | None = Field(default=None, description="参考音频，支持 upload/path/data_uri 或旧字符串格式。")
    reference_text: str | None = Field(default=None, description="参考音频对应文本。")
    speed: float = Field(default=1.0, description="语速。")
    pitch: float = Field(default=0.0, description="音高偏移。")
    volume: float = Field(default=1.0, description="音量倍率。")
    emotion: str | None = Field(default=None, description="情绪标签。")
    emotion_intensity: float | None = Field(default=None, description="情绪强度。")
    instruction: str | None = Field(default=None, description="模型指令或风格提示。")
    extra: dict[str, Any] = Field(default_factory=dict, description="模型专属扩展参数。")


@dataclass(frozen=True)
class GenerateSchemaSpec:
    task: str
    input_model: type[BaseModel]
    parameters_model: type[BaseModel]
    examples: list[dict[str, Any]]

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def parameters_schema(self) -> dict[str, Any]:
        return self.parameters_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return GenerateOutputOptions.model_json_schema()


STABLE_AUDIO3_EXAMPLE = {
    "name": "Stable Audio 3 - 音效生成",
    "request": {
        "model": "stable-audio-3-small-sfx",
        "task": "audio.generate",
        "input": {"prompt": "short cinematic whoosh impact"},
        "parameters": {
            "negative_prompt": "",
            "duration": 7,
            "steps": 8,
            "cfg_scale": 1.0,
            "seed": 1234,
            "batch_size": 1,
            "truncate_output_to_duration": True,
        },
        "output": {"format": "wav", "sample_rate": 44100},
    },
}

TTS_JSON_EXAMPLE = {
    "name": "TTS - JSON 合成",
    "request": {
        "model": "local_f5_tts",
        "task": "tts.speech",
        "input": {"text": "你好，测试成功。", "voice": "f5-default", "language": "zh"},
        "parameters": {
            "reference_audio": {"kind": "path", "path": "E:/audio/ref.wav"},
            "reference_text": "参考文本",
            "speed": 1.0,
            "extra": {},
        },
        "output": {"format": "wav", "sample_rate": 24000},
    },
}

TTS_MULTIPART_EXAMPLE = {
    "name": "TTS - multipart 上传参考音频",
    "request": {
        "model": "local_f5_tts",
        "task": "tts.speech",
        "input": {"text": "你好，测试成功。", "voice": "f5-default", "language": "zh"},
        "parameters": {"reference_audio": {"kind": "upload", "field": "ref_audio"}, "speed": 1.0},
        "output": {"format": "wav", "sample_rate": 24000},
    },
}


STABLE_AUDIO3_SPEC = GenerateSchemaSpec(
    task="audio.generate",
    input_model=StableAudio3Input,
    parameters_model=StableAudio3Parameters,
    examples=[STABLE_AUDIO3_EXAMPLE],
)

TTS_SPEC = GenerateSchemaSpec(
    task="tts.speech",
    input_model=TTSInput,
    parameters_model=TTSParameters,
    examples=[TTS_JSON_EXAMPLE, TTS_MULTIPART_EXAMPLE],
)


class GenerateSchemaValidationError(ValueError):
    def __init__(self, section: str, exc: ValidationError):
        self.section = section
        self.errors = _prefix_errors(section, exc)
        first_error = self.errors[0] if self.errors else {"loc": [section], "msg": "Invalid value"}
        dotted_path = ".".join(str(part) for part in first_error["loc"])
        super().__init__(f"{dotted_path}: {first_error['msg']}")


def _prefix_errors(section: str, exc: ValidationError) -> list[dict[str, Any]]:
    errors = []
    for error in exc.errors(include_url=False):
        clean_error = {key: value for key, value in error.items() if key != "ctx"}
        clean_error["loc"] = [section, *clean_error.get("loc", [])]
        errors.append(clean_error)
    return errors


def get_generate_schema_spec(model_id: str, tasks: list[str]) -> GenerateSchemaSpec | None:
    if model_id == "stable-audio-3-small-sfx":
        return STABLE_AUDIO3_SPEC
    if "tts.speech" in tasks:
        return TTS_SPEC
    return None


def schema_payload_for_model(model_id: str, tasks: list[str]) -> dict[str, Any]:
    spec = get_generate_schema_spec(model_id, tasks)
    if spec is None:
        return {"input_schema": None, "parameters_schema": None, "output_schema": None, "examples": []}
    return {
        "input_schema": spec.input_schema(),
        "parameters_schema": spec.parameters_schema(),
        "output_schema": spec.output_schema(),
        "examples": spec.examples,
    }


def validate_generate_request_schema(request: GenerateRequest, tasks: list[str]) -> GenerateRequest:
    spec = get_generate_schema_spec(request.model, tasks)
    if spec is None:
        return request
    try:
        request.input = convert_file_inputs(
            spec.input_model.model_validate(request.input).model_dump(mode="python", exclude_none=True)
        )
        request.parameters = convert_file_inputs(
            spec.parameters_model.model_validate(request.parameters).model_dump(mode="python", exclude_none=True)
        )
    except ValidationError as exc:
        section = "input" if exc.title == spec.input_model.__name__ else "parameters"
        raise GenerateSchemaValidationError(section, exc) from exc
    return request


def generate_json_openapi_examples() -> dict[str, dict[str, Any]]:
    return {
        "stable-audio3": {
            "summary": STABLE_AUDIO3_EXAMPLE["name"],
            "value": STABLE_AUDIO3_EXAMPLE["request"],
        },
        "tts-json": {
            "summary": TTS_JSON_EXAMPLE["name"],
            "value": TTS_JSON_EXAMPLE["request"],
        },
    }
