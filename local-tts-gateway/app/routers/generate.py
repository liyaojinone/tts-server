from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.core.exceptions import GatewayError
from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.generate import GenerateRequest, ModelInfo
from app.schemas.voice import VoiceResponse
from app.services.file_inputs import cleanup_temp_files, resolve_generation_files


router = APIRouter()


def _error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


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
    try:
        request, uploads = await _parse_generate_request(http_request)
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
    except ValidationError as exc:
        return _error_response(400, "INVALID_REQUEST", "Request validation failed", {"errors": exc.errors()})
    except GatewayError as exc:
        return _error_response(404, exc.code, exc.message, exc.details)
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
