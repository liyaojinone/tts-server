from fastapi import FastAPI

from app.routers.clone import router as clone_router
from app.routers.health import router as health_router
from app.routers.providers import router as providers_router
from app.routers.synthesize import router as synthesize_router
from app.services.process_manager import ProcessManager
from app.services.provider_registry import ProviderRegistry


def create_app() -> FastAPI:
    app = FastAPI(title="Local TTS Gateway", version="0.1.0")
    registry = ProviderRegistry.from_directory()
    app.state.provider_registry = registry
    app.state.process_manager = ProcessManager(registry.provider_map)

    app.include_router(clone_router)
    app.include_router(health_router)
    app.include_router(providers_router)
    app.include_router(synthesize_router)
    return app
