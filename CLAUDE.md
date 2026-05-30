# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

通用本地 TTS 协议服务集合。核心思路：各 TTS 引擎（CosyVoice、F5-TTS、GPT-SoVITS、Index-TTS、VoxCPM）作为独立子进程运行，由 `local-tts-gateway` 统一代理并暴露一致的 HTTP API；`local-tts-protocol` 定义共享 Pydantic 模型，`local-tts-service-kit` 提供 FastAPI 服务装配能力。

## 项目结构

```
local-tts-protocol/      共享协议 Pydantic 模型 (models.py)
local-tts-service-kit/   通用 FastAPI 服务装配 + 异常映射 + ProfileStore
local-tts-gateway/       统一网关 (app/adapters/、app/routers/、app/services/)
services/                各 TTS 引擎的协议适配服务
configs/providers/       每个 provider 的启动配置 *.yaml
docs/                    设计与接口文档
```

## 关键命令

各子模块是独立 Python 包，在对应目录执行。

```bash
# Gateway (Python 3.10+)
cd local-tts-gateway
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090
python -m pytest tests -v

# 各 Service (Python 3.9+)
cd services/gptsovits-service
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5103
```

联调：先启动具体 `services/*`，再启动 `local-tts-gateway/`。

## 架构要点

### 协议层 (`local-tts-protocol`)
- `models.py` 定义 `Voice`、`SynthesizeRequest`、`CloneRequest`、`DesignRequest`、`HealthResponse`、`ErrorResponse` 等 Pydantic 模型，被所有子模块共享。

### 服务装配层 (`local-tts-service-kit`)
- `app.py` 的 `create_service_app(service_name, handler)` 自动装配 /v1/health、/v1/voices、/v1/synthesize、/v1/synthesize/stream、/v1/clone、/v1/clone/{task_id}/status、/v1/design 七个端点。handler 只需实现对应方法即可，未实现的端点返回 404。
- `errors.py` 定义 `ProtocolError` 异常类，`map_exception()` 将各类异常映射为标准错误响应。
- `profiles.py` 提供 `ProfileStore` 用于音色 profile 的持久化。

### Gateway (`local-tts-gateway`)
- **ProviderConfig**：`schemas/provider.py:38` 从 `configs/providers/*.yaml` 加载每个 provider 的 runtime（启动命令、超时）、network（base_url、端口）、capabilities、预定义 voices 等配置。
- **ProcessManager**：`services/process_manager.py` 管理子进程生命周期，启动时调用 provider 配置的 command 并以 healthcheck 轮询确认就绪。使用 asyncio.Lock 控制并发启动。
- **ProviderRegistry**：`services/provider_registry.py` 管理 provider_id → adapter 映射，`from_directory()` 从 YAML 配置加载。
- **Adapter 模式**：`adapters/` 下每个 provider 有一个 adapter（如 `GPTSoVITSAdapter`），负责将统一的 `UnifiedSynthesizeRequest` 映射为下游服务的具体请求体。
- **路由层**：
  - `/v1/providers` 系列（providers.py）：列举、查询 provider 及其 voices
  - `/v1/providers/{id}/synthesize`、`/v1/synthesize`（synthesize.py）：合成请求，自动启动 provider 子进程
  - `/internal/` 系列（internal.py）：provider 运行状态查询与控制（start/stop/restart）
  - `/v1/health`（health.py）：gateway 自身健康检查

### Service 模式（`services/*`）
每个 service 的 `app/main.py` 调用 `create_service_app(service_name, handler)` 创建 FastAPI app，handler 文件包含具体 TTS 引擎的调用逻辑。`app/handler.py` 是实现核心，需提供 `health()`、`list_voices()`、`synthesize()` 等方法，可选实现 `clone()`、`design()`、`stream_synthesize()`。

## 配置说明

- `configs/providers/*.yaml`：每个 provider 一个文件，`provider_type` 决定使用哪个 adapter（映射关系见 `provider_registry.py:25-33`）
- Gateway 自身配置在 `configs/gateway.yaml`
- 服务认证通过环境变量 `LOCAL_TTS_API_KEY` 控制，设置后所有请求需带 `Authorization: Bearer <key>` 头

## 编码规范

- Python 3.9+（gateway 需 3.10+）
- 4 空格缩进，`snake_case` 命名，测试文件 `test_*.py`
- 测试用 `pytest` + `fastapi.testclient.TestClient`
- 路由放 `app/routers/`，共享逻辑沉淀到 protocol 或 service-kit，避免各服务重复实现
- 提交格式：`feat:` / `fix:` 前缀，祈使式主题
