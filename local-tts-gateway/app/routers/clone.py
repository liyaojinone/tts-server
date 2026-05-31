from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies import get_process_manager, get_provider_registry


router = APIRouter()


@router.post("/v1/providers/{provider_id}/clone")
async def clone(
    provider_id: str,
    audio: UploadFile = File(...),
    text: str = Form(default=""),
    name: str = Form(default=""),
    language: str = Form(default="zh"),
    emotion: str = Form(default=""),
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    provider = registry.get_provider(provider_id)
    await manager.ensure_started(provider_id)
    adapter = registry.get_adapter(provider_id)
    return await adapter.clone(
        provider,
        audio=audio,
        text=text,
        name=name,
        language=language,
        emotion=emotion,
    )
