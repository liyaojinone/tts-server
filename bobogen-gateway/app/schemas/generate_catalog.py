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


class ASRInput(DynamicInputModel):
    audio: FileInput | str = Field(..., description="待识别音频，支持 upload/path/data_uri 或本地路径字符串。")
    language: str = Field(default="auto", description="识别语言；auto 为自动识别，可传 Chinese、English 等 Qwen3-ASR 语言名。")


class ASRParameters(DynamicParametersModel):
    mode: str = Field(default="offline", description="识别模式；第一版仅支持 offline。")
    timestamps: bool = Field(default=False, description="是否返回时间戳。")


class AudioAlignInput(DynamicInputModel):
    audio: FileInput | str = Field(..., description="待对齐音频，支持 upload/path/data_uri 或本地路径字符串。")
    text: str = Field(..., description="需要对齐到音频的可信文本。")
    language: str = Field(..., description="语言名，例如 Chinese、English。")
    clip_start: float = Field(default=0.0, description="音频片段在工程时间线上的开始秒数。")


class AudioAlignParameters(DynamicParametersModel):
    granularity: str = Field(default="word", description="对齐粒度；第一版透传模型结果并规范化为 segment。")


class AudioDiarizeInput(DynamicInputModel):
    audio: FileInput | str = Field(..., description="待区分说话人的音频，支持 upload/path/data_uri 或本地路径字符串。")
    clip_start: float = Field(default=0.0, description="音频片段在工程时间线上的开始秒数。")


class AudioDiarizeParameters(DynamicParametersModel):
    oracle_num: int | None = Field(default=None, description="可选的已知说话人数；为空时由模型自动估计。")
    min_duration: float = Field(default=0.0, description="过滤短片段的最小时长，单位秒。")


class ASROutputOptions(GenerateOutputOptions):
    format: str = "json"


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
    output_model: type[BaseModel] = GenerateOutputOptions

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def parameters_schema(self) -> dict[str, Any]:
        return self.parameters_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


def _stable_audio3_example(model_id: str) -> dict[str, Any]:
    return {
        "name": "Stable Audio 3 - 音效生成",
        "request": {
            "model": model_id,
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


def _qwen3_asr_example(model_id: str) -> dict[str, Any]:
    return {
        "name": "Qwen3-ASR - 音频转写",
        "request": {
            "model": model_id,
            "task": "asr.transcribe",
            "input": {
                "audio": {"kind": "upload", "field": "audio"},
                "language": "auto",
            },
            "parameters": {
                "mode": "offline",
                "timestamps": False,
            },
            "output": {"format": "json"},
        },
    }


def _qwen3_forced_aligner_example(model_id: str) -> dict[str, Any]:
    return {
        "name": "Qwen3 ForcedAligner - 台词音频对齐",
        "request": {
            "model": model_id,
            "task": "audio.align",
            "input": {
                "audio": {"kind": "upload", "field": "audio"},
                "text": "你终于来了。",
                "language": "Chinese",
                "clip_start": 120.0,
            },
            "parameters": {
                "granularity": "word",
            },
            "output": {"format": "json"},
        },
    }


def _campplus_speaker_diarization_example(model_id: str) -> dict[str, Any]:
    return {
        "name": "CAM++ Speaker Diarization - 说话人区分",
        "request": {
            "model": model_id,
            "task": "audio.diarize",
            "input": {
                "audio": {"kind": "upload", "field": "audio"},
                "clip_start": 0.0,
            },
            "parameters": {
                "oracle_num": None,
                "min_duration": 0.0,
            },
            "output": {"format": "json"},
        },
    }


STABLE_AUDIO3_EXAMPLE = _stable_audio3_example("stable_audio_3_small_sfx")
QWEN3_ASR_EXAMPLE = _qwen3_asr_example("qwen3_asr_0_6b")
QWEN3_FORCED_ALIGNER_EXAMPLE = _qwen3_forced_aligner_example("qwen3_forced_aligner_0_6b")
CAMPPLUS_SPEAKER_DIARIZATION_EXAMPLE = _campplus_speaker_diarization_example("campplus_speaker_diarization")

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

QWEN3_ASR_SPEC = GenerateSchemaSpec(
    task="asr.transcribe",
    input_model=ASRInput,
    parameters_model=ASRParameters,
    output_model=ASROutputOptions,
    examples=[QWEN3_ASR_EXAMPLE],
)

QWEN3_FORCED_ALIGNER_SPEC = GenerateSchemaSpec(
    task="audio.align",
    input_model=AudioAlignInput,
    parameters_model=AudioAlignParameters,
    output_model=ASROutputOptions,
    examples=[QWEN3_FORCED_ALIGNER_EXAMPLE],
)

CAMPPLUS_SPEAKER_DIARIZATION_SPEC = GenerateSchemaSpec(
    task="audio.diarize",
    input_model=AudioDiarizeInput,
    parameters_model=AudioDiarizeParameters,
    output_model=ASROutputOptions,
    examples=[CAMPPLUS_SPEAKER_DIARIZATION_EXAMPLE],
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
    if model_id in {"stable_audio_3_small_sfx", "stable_audio_3_small_music", "stable_audio_3_medium"}:
        return GenerateSchemaSpec(
            task="audio.generate",
            input_model=StableAudio3Input,
            parameters_model=StableAudio3Parameters,
            examples=[_stable_audio3_example(model_id)],
        )
    if model_id in {"qwen3_asr_0_6b", "qwen3_asr_1_7b"}:
        return GenerateSchemaSpec(
            task="asr.transcribe",
            input_model=ASRInput,
            parameters_model=ASRParameters,
            output_model=ASROutputOptions,
            examples=[_qwen3_asr_example(model_id)],
        )
    if model_id == "qwen3_forced_aligner_0_6b":
        return GenerateSchemaSpec(
            task="audio.align",
            input_model=AudioAlignInput,
            parameters_model=AudioAlignParameters,
            output_model=ASROutputOptions,
            examples=[_qwen3_forced_aligner_example(model_id)],
        )
    if model_id == "campplus_speaker_diarization":
        return CAMPPLUS_SPEAKER_DIARIZATION_SPEC
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
        "stable-audio3-medium": {
            "summary": "Stable Audio 3 Medium - 音频生成",
            "value": _stable_audio3_example("stable_audio_3_medium")["request"],
        },
        "tts-json": {
            "summary": TTS_JSON_EXAMPLE["name"],
            "value": TTS_JSON_EXAMPLE["request"],
        },
    }
