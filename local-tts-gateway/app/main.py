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
    app = FastAPI(title="Local TTS Gateway", version="0.1.0")
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
