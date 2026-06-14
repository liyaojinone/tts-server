from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.exceptions import GatewayError
from app.dependencies import get_process_manager, get_provider_registry


router = APIRouter()


def _error_response(status_code: int, exc: GatewayError) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


def _gateway_error_status(exc: GatewayError) -> int:
    if exc.code == "PROVIDER_NOT_FOUND":
        return 404
    if exc.code == "PROVIDER_DISABLED":
        return 403
    if exc.code in {"PROVIDER_EXTERNAL_START_REQUIRED", "PROVIDER_START_TIMEOUT", "PROVIDER_UNAVAILABLE"}:
        return 503
    return 400


# ---- 管理：列表 & 状态（/v1/ 直接访问） ----

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


@router.get("/v1/providers/status")
async def all_providers_status(manager=Depends(get_process_manager)):
    providers = [
        {
            "provider_id": state.provider_id,
            "status": state.status,
            "pid": state.pid,
            "port": state.port,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "last_used_at": state.last_used_at.isoformat() if state.last_used_at else None,
            "startup_attempts": state.startup_attempts,
            "last_error": state.last_error,
        }
        for state in manager.list_states()
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


# ---- 管理：列表 & 状态（/{provider_id}/v1/ 客户端前缀） ----

@router.get("/{scope_id}/v1/providers")
async def list_providers_scoped(registry=Depends(get_provider_registry)):
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


@router.get("/{scope_id}/v1/providers/status")
async def all_providers_status_scoped(manager=Depends(get_process_manager)):
    providers = [
        {
            "provider_id": state.provider_id,
            "status": state.status,
            "pid": state.pid,
            "port": state.port,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "last_used_at": state.last_used_at.isoformat() if state.last_used_at else None,
            "startup_attempts": state.startup_attempts,
            "last_error": state.last_error,
        }
        for state in manager.list_states()
    ]
    return {"providers": providers}


@router.get("/{scope_id}/v1/providers/{provider_id}")
async def get_provider_scoped(scope_id: str, provider_id: str, registry=Depends(get_provider_registry)):
    provider = registry.get_provider(provider_id)
    return {
        "provider_id": provider.provider_id,
        "provider_type": provider.provider_type,
        "display_name": provider.display_name,
        "enabled": provider.enabled,
    }


# ---- 引擎代理 ----

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


# ---- 运维：生命周期（/{target_id} 是操作目标，可以是任意 provider） ----

@router.post("/v1/providers/{provider_id}/start")
async def start_provider(provider_id: str, manager=Depends(get_process_manager)):
    try:
        state = await manager.start(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": state.status}


@router.post("/v1/providers/{provider_id}/stop")
async def stop_provider(provider_id: str, manager=Depends(get_process_manager)):
    try:
        await manager.stop(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": "stopped"}


@router.post("/v1/providers/{provider_id}/restart")
async def restart_provider(provider_id: str, manager=Depends(get_process_manager)):
    try:
        state = await manager.restart(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": state.status}


# 客户端前缀版本

@router.post("/{scope_id}/v1/providers/{provider_id}/start")
async def start_provider_scoped(scope_id: str, provider_id: str, manager=Depends(get_process_manager)):
    try:
        state = await manager.start(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": state.status}


@router.post("/{scope_id}/v1/providers/{provider_id}/stop")
async def stop_provider_scoped(scope_id: str, provider_id: str, manager=Depends(get_process_manager)):
    try:
        await manager.stop(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": "stopped"}


@router.post("/{scope_id}/v1/providers/{provider_id}/restart")
async def restart_provider_scoped(scope_id: str, provider_id: str, manager=Depends(get_process_manager)):
    try:
        state = await manager.restart(provider_id)
    except GatewayError as exc:
        return _error_response(_gateway_error_status(exc), exc)
    return {"provider_id": provider_id, "status": state.status}


# ---- 运维：日志 ----

@router.get("/v1/providers/{provider_id}/logs")
async def provider_logs(
    provider_id: str,
    stream: str = Query(default="stderr", pattern="^(stdout|stderr)$"),
    lines: int = Query(default=100, ge=1, le=2000),
    manager=Depends(get_process_manager),
):
    return {"provider_id": provider_id, "stream": stream, "lines": lines, "content": manager.get_logs(provider_id, stream, lines)}


@router.get("/{scope_id}/v1/providers/{provider_id}/logs")
async def provider_logs_scoped(
    scope_id: str,
    provider_id: str,
    stream: str = Query(default="stderr", pattern="^(stdout|stderr)$"),
    lines: int = Query(default=100, ge=1, le=2000),
    manager=Depends(get_process_manager),
):
    return {"provider_id": provider_id, "stream": stream, "lines": lines, "content": manager.get_logs(provider_id, stream, lines)}
