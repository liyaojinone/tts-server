from fastapi import APIRouter, Depends

from app.dependencies import get_process_manager, get_provider_registry


router = APIRouter()


# ---- 管理路由 ----

@router.get("/v1/providers")
async def list_providers(registry=Depends(get_provider_registry)):
    providers = [
        {
            "provider_id": provider.provider_id,
            "provider_type": provider.provider_type,
            "display_name": provider.display_name,
            "enabled": provider.enabled,
        }
        for provider in registry.list_providers()
    ]
    return {"providers": providers}


@router.get("/v1/providers/{provider_id}")
async def get_provider(provider_id: str, registry=Depends(get_provider_registry)):
    provider = registry.get_provider(provider_id)
    return {
        "provider_id": provider.provider_id,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "enabled": provider.enabled,
    }


# ---- 引擎代理路由 ----

@router.get("/{provider_id}/v1/health")
async def provider_health(provider_id: str, manager=Depends(get_process_manager)):
    state = manager.get_state(provider_id)
    return {"provider_id": provider_id, "status": state.status}


@router.get("/{provider_id}/v1/voices")
async def provider_voices(provider_id: str, registry=Depends(get_provider_registry)):
    provider = registry.get_provider(provider_id)
    adapter = registry.get_adapter(provider_id)
    result = await adapter.list_voices(provider)
    return result.model_dump()
