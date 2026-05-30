from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError

from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.synthesize import ProviderSynthesizeRequest, UnifiedSynthesizeRequest
from app.services.audio_service import build_audio_response


router = APIRouter()


def _extract_files(form) -> dict:
    """Extract file uploads from multipart form for forwarding."""
    files = {}
    for key in ("reference_audio", "emotion_reference_audio"):
        f = form.get(key)
        if f is not None and hasattr(f, "filename"):
            files[key] = (f.filename, f.file, f.content_type)
    return files or None


@router.post("/v1/providers/{provider_id}/synthesize")
async def synthesize(
    provider_id: str,
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        request_json = str(form.get("request") or "{}")
        request = UnifiedSynthesizeRequest.model_validate_json(request_json)
        files = _extract_files(form)
    else:
        body = await http_request.json()
        request = UnifiedSynthesizeRequest.model_validate(body)
        files = None

    provider = registry.get_provider(provider_id)
    await manager.ensure_started(provider_id)
    adapter = registry.get_adapter(provider_id)
    audio = await adapter.synthesize(provider, request, files=files)
    return build_audio_response(provider_id, audio)


@router.post("/v1/synthesize")
async def synthesize_alias(
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        request_json = str(form.get("request") or "{}")
        request = ProviderSynthesizeRequest.model_validate_json(request_json)
        files = _extract_files(form)
    else:
        body = await http_request.json()
        request = ProviderSynthesizeRequest.model_validate(body)
        files = None

    provider = registry.get_provider(request.provider_id)
    await manager.ensure_started(request.provider_id)
    adapter = registry.get_adapter(request.provider_id)
    audio = await adapter.synthesize(provider, request, files=files)
    return build_audio_response(request.provider_id, audio)
