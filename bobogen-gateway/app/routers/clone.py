from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies import get_process_manager, get_provider_registry


router = APIRouter()


@router.post(
    "/{provider_id}/v1/clone",
    tags=["04 Legacy Provider 旧接口"],
    summary="旧接口：克隆并注册音色",
    description="上传参考音频并注册 provider 本地音色。新协议稳定前保留此兼容接口。",
)
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
