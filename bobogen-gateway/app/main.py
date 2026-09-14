import httpx
from fastapi import FastAPI

from app.config import REPO_ROOT
from app.routers.clone import router as clone_router
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.management import MODEL_CATALOG, INSTALLER_LOG, router as management_router
from app.routers.providers import router as providers_router
from app.routers.synthesize import router as synthesize_router
from app.services.process_manager import ProcessManager
from app.services.job_store import GatewayJobStore
from app.services.model_installer import ModelInstallManager
from app.services.huggingface_token import HuggingFaceTokenStore
from app.services.model_source import ModelSourceConfigStore
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
        {"name": "06 模型服务管理", "description": "查看本地模型目录、资源检测和服务控制台。"},
    ]
    app = FastAPI(
        title="BoboGen Gateway",
        version="0.1.0",
        description="BoboGen Server 统一生成网关。Postman/Apifox 可直接导入 `/openapi.json`。",
        openapi_tags=tags_metadata,
    )
    registry = ProviderRegistry.from_directory()
    source_config_store = ModelSourceConfigStore(REPO_ROOT / "runtime" / "model-source-config.json")
    huggingface_token_store = HuggingFaceTokenStore(
        REPO_ROOT / "runtime" / "secrets" / "huggingface-token.bin"
    )
    manager = ProcessManager(
        registry.provider_map,
        source_config_store=source_config_store,
        huggingface_token_store=huggingface_token_store,
    )
    app.state.provider_registry = registry
    app.state.process_manager = manager
    app.state.model_source_config_store = source_config_store
    app.state.huggingface_token_store = huggingface_token_store
    app.state.job_store = GatewayJobStore()
    async def prefetch_model_weights(model_id: str) -> None:
        """让引擎的官方运行时真正下载/加载权重（upstream_managed 模型）。"""
        provider = registry.get_provider_by_model(model_id)
        await manager.ensure_started(provider.provider_id)
        base_url = provider.network.base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=1800.0) as client:
            response = await client.post(f"{base_url}/v1/warmup")
            if response.status_code == 404:
                # 引擎未实现 warmup，权重仍会在首次实际使用时由官方机制加载。
                return
            if response.status_code >= 400:
                raise RuntimeError(
                    f"权重预取失败: HTTP {response.status_code} {response.text[:200]}"
                )

    app.state.model_install_manager = ModelInstallManager(
        REPO_ROOT,
        MODEL_CATALOG,
        log_path=INSTALLER_LOG,
        source_config_store=source_config_store,
        huggingface_token_store=huggingface_token_store,
        prefetch=prefetch_model_weights,
    )

    app.include_router(clone_router)
    app.include_router(generate_router)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(management_router)
    app.include_router(providers_router)
    app.include_router(synthesize_router)

    if init_mcp is not None and mcp_server is not None:
        init_mcp(registry, manager)
        app.mount("/mcp", mcp_server.sse_app())

    return app
