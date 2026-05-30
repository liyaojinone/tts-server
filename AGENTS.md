# Repository Guidelines

## 项目结构与模块组织
本仓库是一个面向本地模型的通用 TTS 协议启动服务集合。`local-tts-protocol/` 定义共享协议模型与测试；`local-tts-service-kit/` 提供通用 FastAPI 服务装配能力；`local-tts-gateway/` 暴露统一网关，并从 `configs/providers/` 读取提供者配置；`services/` 下包含 `cosyvoice-service`、`f5tts-service`、`gptsovits-service` 三个协议适配服务。设计与实现文档放在 `docs/`，优先补充到对应专题文件。

## 构建、测试与本地开发
各子模块均为独立 Python 包，建议在对应目录执行命令。

```bash
cd local-tts-gateway
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090
python -m pytest tests -v
```

服务模块启动方式类似，例如：

```bash
cd services/f5tts-service
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5102
```

若需联调，先启动具体 `services/*`，再启动 `local-tts-gateway/`。

## 编码风格与命名约定
统一使用 Python 3.9+；`local-tts-gateway` 需要 Python 3.10+。沿用现有风格：4 空格缩进，模块与文件名使用 `snake_case`，测试文件命名为 `test_*.py`。FastAPI 路由放在 `app/routers/`，共享逻辑优先沉淀到 `local-tts-protocol` 或 `local-tts-service-kit`，避免在具体服务内重复实现。

## 测试规范
当前测试框架为 `pytest`，并广泛使用 `fastapi.testclient.TestClient`。新增接口、适配映射、配置加载或进程管理逻辑时，必须补充对应单元测试。优先覆盖协议兼容性、健康检查、音色枚举和合成请求的成功/失败路径。

## 提交与合并请求
当前聚合目录未包含 `.git`，无法直接读取统一提交历史；新增提交请使用简洁、祈使式主题，推荐格式如 `feat: add gptsovits clone status endpoint`、`fix: normalize provider healthcheck error`。PR 应说明影响的模块、启动/测试命令，以及接口变更；若修改 HTTP 返回结构，请附示例请求或响应片段。

## 配置与安全提示
不要提交本机模型权重、缓存文件、参考音频或绝对路径配置。`configs/providers/*.yaml` 中的工作目录、端口和启动命令应保持可复现，并优先使用 `127.0.0.1` 进行本地服务绑定。
