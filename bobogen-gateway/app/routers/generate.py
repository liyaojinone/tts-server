from io import BytesIO
import json
import logging
import math
from pathlib import Path
import struct
import time
import wave

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.core.exceptions import GatewayError
from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.generate import GenerateRequest, ModelInfo
from app.schemas.voice import VoiceResponse
from app.services.file_inputs import cleanup_temp_files, resolve_generation_files


router = APIRouter()
logger = logging.getLogger("bobogen_gateway.generate")
LOG_FILE = Path("logs") / "gateway.log"


def _shorten(value: str, limit: int = 360) -> str | dict:
    if value.startswith("data:"):
        return {"kind": "data-uri", "length": len(value)}
    if len(value) <= limit:
        return value
    return {"preview": value[:limit], "length": len(value)}


def _sanitize(value, key: str = ""):
    if isinstance(value, (bytes, bytearray)):
        return {"kind": "bytes", "length": len(value)}
    if isinstance(value, str):
        if key.lower() in {"data", "audio", "content", "bytes", "blob"}:
            return _shorten(value, limit=120)
        return _shorten(value)
    if isinstance(value, dict):
        return {item_key: _sanitize(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _sanitize(value.model_dump(mode="json"))
    return value


def _describe_audio_bytes(content: bytes, content_type: str) -> dict:
    summary = {"contentType": content_type, "bytes": len(content)}
    if not content.startswith(b"RIFF"):
        return summary
    try:
        with wave.open(BytesIO(content), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            frame_bytes = wav.readframes(frames)
    except (EOFError, wave.Error) as exc:
        summary["wavError"] = str(exc)
        return summary

    summary.update(
        {
            "format": "wav",
            "channels": channels,
            "sampleRate": sample_rate,
            "sampleWidth": sample_width,
            "frames": frames,
            "durationSeconds": round(frames / sample_rate, 3) if sample_rate else None,
        }
    )

    peak = 0.0
    sum_squares = 0.0
    sample_count = 0
    if sample_width == 2:
        for (sample,) in struct.iter_unpack("<h", frame_bytes[: len(frame_bytes) - (len(frame_bytes) % 2)]):
            normalized = sample / 32768.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1
    elif sample_width == 4:
        for (sample,) in struct.iter_unpack("<i", frame_bytes[: len(frame_bytes) - (len(frame_bytes) % 4)]):
            normalized = sample / 2147483648.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1
    elif sample_width == 1:
        for sample in frame_bytes:
            normalized = (sample - 128) / 128.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1

    if sample_count:
        summary["peak"] = round(peak, 6)
        summary["rms"] = round(math.sqrt(sum_squares / sample_count), 6)
        summary["silent"] = peak == 0
    return summary


def _emit_generate_log(event: str, payload: dict) -> None:
    line = f"{event} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    logger.info(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError:
        logger.debug("failed to append gateway generate log", exc_info=True)


def _error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def _gateway_error_status(exc: GatewayError) -> int:
    if exc.code in {"MODEL_NOT_FOUND", "PROVIDER_NOT_FOUND"}:
        return 404
    if exc.code == "PROVIDER_DISABLED":
        return 403
    if exc.code in {"PROVIDER_EXTERNAL_START_REQUIRED", "PROVIDER_START_TIMEOUT", "PROVIDER_UNAVAILABLE"}:
        return 503
    return 400


def _outputs_for_tasks(tasks: list[str]) -> list[str]:
    if any(task.startswith("tts.") or task.startswith("audio.") for task in tasks):
        return ["audio/wav"]
    return []


def _capabilities_for_provider(provider) -> dict:
    return {
        "reference_audio": provider.capabilities.synthesize,
        "emotion_reference_audio": provider.provider_type in {"indextts"},
        "instruction": provider.provider_type in {"voxcpm", "cosyvoice"},
        "clone": provider.capabilities.clone,
        "stream": provider.capabilities.stream,
    }


def _model_info(model_id: str, provider, tasks: list[str]) -> ModelInfo:
    voices = [
        VoiceResponse(
            voice_id=voice.voice_id,
            name=voice.name,
            language=voice.language,
            gender=voice.gender,
            description=voice.description,
            tags=voice.tags,
            metadata=voice.metadata,
        )
        for voice in provider.voices
    ]
    return ModelInfo(
        id=model_id,
        name=provider.display_name,
        provider_id=provider.provider_id,
        tasks=tasks,
        outputs=_outputs_for_tasks(tasks),
        enabled=provider.enabled,
        voices=voices,
        capabilities=_capabilities_for_provider(provider),
    )


async def _parse_generate_request(http_request: Request) -> tuple[GenerateRequest, dict]:
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        request_json = str(form.get("request") or "{}")
        uploads = {
            key: value
            for key, value in form.items()
            if hasattr(value, "filename") and hasattr(value, "read")
        }
        return GenerateRequest.model_validate_json(request_json), uploads

    return GenerateRequest.model_validate(await http_request.json()), {}


@router.get("/v1/models")
async def list_models(registry=Depends(get_provider_registry)):
    return {
        "models": [
            _model_info(model_id, provider, tasks).model_dump()
            for model_id, provider, tasks in registry.list_models()
        ]
    }


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str, registry=Depends(get_provider_registry)):
    try:
        provider = registry.get_provider_by_model(model_id)
    except GatewayError as exc:
        return _error_response(404, exc.code, exc.message, exc.details)
    return _model_info(model_id, provider, registry.get_model_tasks(provider)).model_dump()


@router.post("/v1/generate")
async def generate(
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    cleanups = []
    started_at = time.perf_counter()
    try:
        request, uploads = await _parse_generate_request(http_request)
        _emit_generate_log(
            "generate.request",
            {
                "model": request.model,
                "task": request.task,
                "input": _sanitize(request.input),
                "parameters": _sanitize(request.parameters),
                "output": _sanitize(request.output),
                "uploadFields": sorted(uploads.keys()),
            },
        )
        provider = registry.get_provider_by_model(request.model)
        tasks = registry.get_model_tasks(provider)
        if request.task not in tasks:
            return _error_response(
                400,
                "UNSUPPORTED_TASK",
                f"Unsupported task for model: {request.task}",
                {"model": request.model, "task": request.task, "supported_tasks": tasks},
            )

        request.input, input_cleanups = await resolve_generation_files(request.input, uploads)
        request.parameters, parameter_cleanups = await resolve_generation_files(request.parameters, uploads)
        cleanups.extend(input_cleanups)
        cleanups.extend(parameter_cleanups)

        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        audio = await adapter.generate(provider, request)
        _emit_generate_log(
            "generate.response",
            {
                "model": request.model,
                "task": request.task,
                "providerId": provider.provider_id,
                "elapsedMs": round((time.perf_counter() - started_at) * 1000, 1),
                "audio": _describe_audio_bytes(audio.content, audio.content_type),
                "durationSeconds": audio.duration_seconds,
                "sampleRate": audio.sample_rate,
            },
        )
    except ValidationError as exc:
        return _error_response(400, "INVALID_REQUEST", "Request validation failed", {"errors": exc.errors()})
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc.code, exc.message, exc.details)
    except ValueError as exc:
        return _error_response(400, "INVALID_REQUEST", str(exc))
    finally:
        cleanup_temp_files(cleanups)

    headers = {
        "X-Provider-Id": provider.provider_id,
        "X-Model-Id": request.model,
        "X-Task": request.task,
    }
    if audio.duration_seconds is not None:
        headers["X-Audio-Duration"] = str(audio.duration_seconds)
    if audio.sample_rate is not None:
        headers["X-Sample-Rate"] = str(audio.sample_rate)
    return Response(content=audio.content, media_type=audio.content_type, headers=headers)
