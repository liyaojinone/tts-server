from fastapi import APIRouter, Depends

from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.synthesize import ProviderSynthesizeRequest, UnifiedSynthesizeRequest
from app.services.audio_service import build_audio_response


router = APIRouter()


@router.post("/v1/providers/{provider_id}/synthesize")
async def synthesize(provider_id: str, request: UnifiedSynthesizeRequest, registry=Depends(get_provider_registry), manager=Depends(get_process_manager)):
    provider = registry.get_provider(provider_id)
    await manager.ensure_started(provider_id)
    adapter = registry.get_adapter(provider_id)
    audio = await adapter.synthesize(provider, request)
    return build_audio_response(provider_id, audio)


@router.post("/v1/synthesize")
async def synthesize_alias(request: ProviderSynthesizeRequest, registry=Depends(get_provider_registry), manager=Depends(get_process_manager)):
    provider = registry.get_provider(request.provider_id)
    await manager.ensure_started(request.provider_id)
    adapter = registry.get_adapter(request.provider_id)
    audio = await adapter.synthesize(provider, request)
    return build_audio_response(request.provider_id, audio)
