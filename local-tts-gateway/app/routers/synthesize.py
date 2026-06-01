from fastapi import APIRouter, Depends, Request

from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.synthesize import UnifiedSynthesizeRequest
from app.services.audio_service import build_audio_response


router = APIRouter()


def _extract_files(form) -> dict:
    files = {}
    for key in ("reference_audio", "emotion_reference_audio"):
        f = form.get(key)
        if f is not None and hasattr(f, "filename"):
            files[key] = (f.filename, f.file, f.content_type)
    return files or None


@router.post("/{provider_id}/v1/synthesize")
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
