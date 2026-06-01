from fastapi import APIRouter, Depends, Query

from app.dependencies import get_process_manager


router = APIRouter()


@router.get("/internal/providers/status")
async def provider_status(manager=Depends(get_process_manager)):
    providers = [
        {
            "provider_id": state.provider_id,
            "status": state.status,
            "pid": state.pid,
            "port": state.port,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "last_health_at": state.last_health_at.isoformat() if state.last_health_at else None,
            "last_used_at": state.last_used_at.isoformat() if state.last_used_at else None,
            "startup_attempts": state.startup_attempts,
            "last_error": state.last_error,
        }
        for state in manager.list_states()
    ]
    return {"providers": providers}


@router.post("/internal/providers/{provider_id}/start")
async def start_provider(provider_id: str, manager=Depends(get_process_manager)):
    state = await manager.start(provider_id)
    return {"provider_id": provider_id, "status": state.status}


@router.post("/internal/providers/{provider_id}/stop")
async def stop_provider(provider_id: str, manager=Depends(get_process_manager)):
    await manager.stop(provider_id)
    return {"provider_id": provider_id, "status": "stopped"}


@router.post("/internal/providers/{provider_id}/restart")
async def restart_provider(provider_id: str, manager=Depends(get_process_manager)):
    state = await manager.restart(provider_id)
    return {"provider_id": provider_id, "status": state.status}


@router.get("/internal/providers/{provider_id}/logs")
async def provider_logs(
    provider_id: str,
    stream: str = Query(default="stderr", pattern="^(stdout|stderr)$"),
    lines: int = Query(default=100, ge=1, le=2000),
    manager=Depends(get_process_manager),
):
    return {"provider_id": provider_id, "stream": stream, "lines": lines, "content": manager.get_logs(provider_id, stream, lines)}
