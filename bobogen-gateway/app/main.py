from fastapi import FastAPI

from app.routers.clone import router as clone_router
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router
from app.routers.providers import router as providers_router
from app.routers.synthesize import router as synthesize_router
from app.services.process_manager import ProcessManager
from app.services.provider_registry import ProviderRegistry

try:
    from app.routers.mcp import init as init_mcp, mcp as mcp_server
except ModuleNotFoundError as exc:
    if exc.name != "mcp":
        raise
    init_mcp = None
    mcp_server = None


def create_app() -> FastAPI:
    tags_metadata = [
        {"name": "00 Health", "description": "Gateway 健康检查和日志查看。"},
        {"name": "01 Models", "description": "统一生成模型发现、能力和动态参数 schema。"},
        {"name": "02 Generate 新统一接口", "description": "推荐使用的新统一音频生成接口。"},
        {"name": "03 Provider 管理", "description": "Provider 列表、状态、生命周期和日志。"},
        {"name": "04 Legacy Provider 旧接口", "description": "兼容旧客户端的 provider 直连风格接口。"},
        {"name": "05 Stable Audio 3 调参", "description": "Stable Audio 3 参数可通过模型详情和统一生成示例查看。"},
    ]
    app = FastAPI(
        title="BoboGen Gateway",
        version="0.1.0",
        description="BoboGen Server 统一生成网关。Postman/Apifox 可直接导入 `/openapi.json`。",
        openapi_tags=tags_metadata,
    )
    registry = ProviderRegistry.from_directory()
    manager = ProcessManager(registry.provider_map)
    app.state.provider_registry = registry
    app.state.process_manager = manager

    app.include_router(clone_router)
    app.include_router(generate_router)
    app.include_router(health_router)
    app.include_router(providers_router)
    app.include_router(synthesize_router)

    if init_mcp is not None and mcp_server is not None:
        init_mcp(registry, manager)
        app.mount("/mcp", mcp_server.sse_app())

    return app
