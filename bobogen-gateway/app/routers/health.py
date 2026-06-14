from pathlib import Path

from fastapi import APIRouter, Query

LOG_FILE = Path("logs") / "gateway.log"


router = APIRouter()


@router.get("/v1/health", tags=["00 Health"], summary="Gateway 健康检查")
async def health():
    return {"status": "ok"}


@router.get("/v1/logs", tags=["00 Health"], summary="查看 Gateway 日志")
async def gateway_logs(lines: int = Query(default=100, ge=1, le=2000)):
    if not LOG_FILE.exists():
        return {"content": ""}
    with open(LOG_FILE, "r") as f:
        all_lines = f.readlines()
    return {"lines": len(all_lines[-lines:]), "content": "".join(all_lines[-lines:])}


@router.get("/{scope_id}/v1/logs", tags=["00 Health"], summary="查看 Gateway 日志（旧 scope 路径）")
async def gateway_logs_scoped(scope_id: str, lines: int = Query(default=100, ge=1, le=2000)):
    if not LOG_FILE.exists():
        return {"content": ""}
    with open(LOG_FILE, "r") as f:
        all_lines = f.readlines()
    return {"lines": len(all_lines[-lines:]), "content": "".join(all_lines[-lines:])}
