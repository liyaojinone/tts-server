# 本地 TTS 统一网关设计文档

> **日期**: 2026-04-02
> **状态**: 设计中
> **目标**: 为 `CosyVoice`、`F5-TTS`、`GPT-SoVITS` 提供统一 HTTP 协议、统一启动方式和可扩展的本地模型接入层

---

## 1. 设计结论

建议采用 **外部统一网关 + 模型适配器 + 进程管理器** 的三层实现，而不是把统一协议直接改进每个模型项目。

原因：

- 当前三套模型的启动方式、依赖环境、输入参数和输出行为差异较大
- 其中部分项目已经被本地改造为便携启动形式，直接侵入原仓库会增加维护成本
- 未来还会扩展其他模型，统一层应放在模型外部，避免重复改造

第一版优先做：

- 统一入口：`GET /v1/health`
- 统一入口：`GET /v1/voices`
- 统一入口：`POST /v1/synthesize`
- 自动拉起模型服务
- 健康检查、预热、超时与重启

第二版再做：

- `POST /v1/clone`
- `POST /v1/synthesize/stream`
- 模型预热缓存
- 并发队列与资源调度

---

## 2. 目标范围

本设计仅聚焦以下 3 个模型：

- `CosyVoice` / Python 3.10
- `F5-TTS` / Python 3.10
- `GPTSoVITS` / Python 3.9

当前不要求：

- 统一训练流程
- 深度改造各模型源码
- 一次性统一全部高级能力
- 第一期就支持所有模型特性完全等价

本设计优先解决的问题是：

1. 其它服务只需要对接一套 HTTP 协议
2. 用户不用手动进入不同目录启动不同模型
3. 模型差异通过配置和 adapter 吸收
4. 后续新增模型时，只需要加一个 adapter 和一段配置

---

## 3. 总体架构

```text
┌────────────────────────────────────────────┐
│               调用方服务                    │
│  只调用统一 HTTP 接口，不关心底层模型差异     │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│             BoboGen Gateway              │
│                                            │
│  - OpenAPI / 路由层                         │
│  - 请求校验                                 │
│  - provider 路由                            │
│  - 参数标准化                               │
│  - 音频响应封装                             │
│  - 错误码统一                               │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│        Provider Adapter + Process Manager   │
│                                            │
│  - cosyvoice adapter                        │
│  - f5-tts adapter                           │
│  - gpt-sovits adapter                       │
│  - 进程启动/探活/重启/停止                   │
│  - 端口分配                                 │
│  - 本地环境与命令适配                        │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│               模型原生服务                  │
│                                            │
│  CosyVoice / F5-TTS / GPT-SoVITS           │
│  尽量复用现有 api.py / webui.py / bat       │
└────────────────────────────────────────────┘
```

---

## 4. 两种接入路线对比

### 方案 A：统一网关直接 import 各模型代码

优点：

- 少一层本地 HTTP 转发
- 理论上性能更高
- 参数映射更灵活

缺点：

- 三个模型依赖冲突概率高
- Python 版本不一致，难以放在一个运行时内
- 对源码侵入强，后续升级模型更麻烦

### 方案 B：统一网关转发到各模型原生服务

优点：

- 每个模型继续运行在自己的 Python 环境里
- 兼容你现在已有的 `bat`、`runtime`、项目内 Python
- 容易做进程管理和单独重启
- 后续扩展新模型成本低

缺点：

- 多一层本地网络转发
- 某些模型原生接口不统一，需要 adapter 做翻译

### 方案 C：混合模式

做法：

- 第一阶段全部走“统一网关 -> 各模型原生服务”
- 后续如果某个模型稳定且值得深度优化，再把它切换为直调模式

**推荐采用方案 C。**

这最适合当前工作区状态，因为现有项目已经具有较明确的独立运行方式，不应一开始就强行合并到一个 Python 进程。

---

## 5. 目录建议

建议在当前工作区新增一个独立网关目录，例如：

```text
E:\AiModel\tts\
  docs\
  bobogen-gateway\
    app\
      main.py
      config.py
      models.py
      errors.py
      routers\
      adapters\
      services\
      utils\
    configs\
      providers\
        cosyvoice.yaml
        f5tts.yaml
        gptsovits.yaml
    scripts\
    tests\
```

设计原则：

- 网关工程与模型工程解耦
- 每个模型独立配置
- 模型目录保持尽量原样

---

## 6. Provider 注册模型

统一网关内部用 `provider_id` 标识具体模型实例，例如：

```json
{
  "provider_id": "cosyvoice-default",
  "provider_type": "cosyvoice",
  "base_url": "http://127.0.0.1:5101",
  "enabled": true
}
```

这样做的意义：

- 一个模型类型可以注册多个实例
- 可以区分不同权重、不同音色集、不同端口
- 应用侧始终通过 `provider_id` 调用，不依赖目录结构

推荐配置字段：

- `provider_id`
- `provider_type`
- `display_name`
- `root_dir`
- `python_env`
- `launch_command`
- `healthcheck_url`
- `voices_url`
- `synthesize_url`
- `startup_timeout_ms`
- `request_timeout_ms`
- `capabilities`
- `parameter_mapping`

---

## 7. 统一协议的落地建议

在现有协议文档基础上，建议统一网关新增一个显式的 provider 维度。

推荐网关侧接口：

- `GET /v1/providers`
- `GET /v1/providers/{provider_id}/health`
- `GET /v1/providers/{provider_id}/voices`
- `POST /v1/providers/{provider_id}/synthesize`

同时保留兼容别名：

- `GET /v1/voices?provider_id=...`
- `POST /v1/synthesize`

原因：

- 对“多模型并存”的场景更清晰
- 不会让 `voice_id` 承担“模型选择 + 音色选择”双重语义
- 便于后续扩展为模型市场或服务注册表

如果调用方已经绑定你的协议草案，也可以先兼容以下请求体：

```json
{
  "provider_id": "gptsovits-default",
  "text": "你好",
  "voice_id": "default",
  "language": "zh",
  "parameters": {
    "speed": 1.0
  },
  "output": {
    "format": "wav"
  }
}
```

---

## 8. 三个模型的适配策略

### 8.1 CosyVoice

当前已知情况：

- 官方推荐 `conda` Python 3.10
- 本地目录内已存在 `py311` 和 [run-api.bat](E:\AiModel\tts\CosyVoice2\CosyVoice\run-api.bat)
- 已有 [api.py](E:\AiModel\tts\CosyVoice2\CosyVoice\api.py) 与 [webui.py](E:\AiModel\tts\CosyVoice2\CosyVoice\webui.py)

建议：

- 优先复用已有 `api.py`
- 若原生接口与统一协议不一致，由 `cosyvoice adapter` 转译
- `voices` 先暴露固定音色/模式列表
- 零样本合成时，统一协议中的 `reference_audio`、`reference_text` 映射到其原生字段

适合承接的统一参数：

- `text`
- `language`
- `voice_id`
- `parameters.speed`
- `parameters.instruction`
- `reference_audio`
- `reference_text`

后续可扩展：

- 流式合成
- instruct 模式
- cross-lingual 模式

### 8.2 F5-TTS

当前已知情况：

- 官方推荐 `conda` Python 3.10
- 本地有 [run-api.bat](E:\AiModel\tts\F5-TTS\run-api.bat) 和 [run-train.bat](E:\AiModel\tts\F5-TTS\run-train.bat)
- 项目内已有 [api.py](E:\AiModel\tts\F5-TTS\api.py)

建议：

- 第一版直接复用 `api.py`
- `voices` 不必追求“传统音色库”语义，可以返回逻辑音色：
  - `f5-default`
  - `f5-multi-style`
  - `f5-clone`
- 参考音频驱动型模型可把 `voice_id` 作为模式选择，而不是真实预置发音人

适合承接的统一参数：

- `text`
- `parameters.speed`
- `reference_audio`
- `reference_text`
- `parameters.extra` 中的采样步数、cfg、seed 等

后续可扩展：

- 多说话人
- 风格切换
- 微调后模型注册

### 8.3 GPT-SoVITS

当前已知情况：

- 官方推荐 `conda` Python 3.9
- 本地整合包模式明显，已有 [go-webui.bat](E:\AiModel\tts\GPT-SoVITS-v2-240821\go-webui.bat) 与 [run_api.bat](E:\AiModel\tts\GPT-SoVITS-v2-240821\run_api.bat)
- 项目内已有 [api.py](E:\AiModel\tts\GPT-SoVITS-v2-240821\api.py)、[api_v2.py](E:\AiModel\tts\GPT-SoVITS-v2-240821\api_v2.py)

建议：

- 第一版优先接现有 API，不直接走 WebUI 自动化
- `voices` 返回已注册权重或配置好的 speaker/profile 列表
- `reference_audio` 与 `reference_text` 映射为 few-shot 合成输入
- 对训练得到的新音色，可在统一网关层做注册，不要求网关感知训练细节

适合承接的统一参数：

- `text`
- `language`
- `voice_id`
- `reference_audio`
- `reference_text`
- `parameters.speed`

后续可扩展：

- `clone`
- 权重切换
- 多语言与分句策略

---

## 9. voices 的统一语义

三种模型对“voice”理解并不一致，必须在网关层做抽象。

推荐统一语义：

- `voice_id` 是“可供调用方选择的一种稳定合成配置”
- 它不一定等于模型原生 speaker 名称
- 它可以代表：
  - 预置音色
  - 某个权重文件
  - 某种推理模式
  - 某个克隆配置模板

例如：

```json
{
  "voice_id": "gptsovits-nahida-zh",
  "name": "Nahida 中文",
  "language": ["zh"],
  "gender": "female",
  "description": "基于 GPT-SoVITS 权重的角色音色",
  "metadata": {
    "provider_type": "gptsovits",
    "native_voice": "nahida_v2",
    "mode": "few_shot"
  }
}
```

这能保证协议稳定，而不暴露底层模型实现细节。

---

## 10. 进程管理器设计

这是整个系统的关键部分。

### 10.1 职责

- 按 provider 配置启动模型服务
- 轮询健康检查直到服务可用
- 跟踪 PID、端口、启动时间、状态
- 在失败时重试或返回明确错误
- 支持“懒启动”

### 10.2 推荐状态机

```text
stopped -> starting -> healthy -> unhealthy -> restarting -> healthy
```

### 10.3 推荐行为

- 网关收到请求时，如果目标 provider 未启动，则自动启动
- 如果启动超过超时阈值，返回 `PROVIDER_START_TIMEOUT`
- 如果健康检查失败，返回 `PROVIDER_UNAVAILABLE`
- 如果进程退出，自动标记为 `stopped`

### 10.4 为什么不直接总是预启动

- 三个模型显存占用较重
- 用户未必同时用三个
- 让网关按需拉起更符合“本地模型工具箱”的使用方式

可选优化：

- 支持启动后空闲 N 分钟自动停止
- 支持“常驻模型白名单”

---

## 11. 启动方式建议

建议统一使用“配置驱动启动”，不要把命令硬编码在业务逻辑里。

例如：

```yaml
provider_id: cosyvoice-default
provider_type: cosyvoice
root_dir: E:\AiModel\tts\CosyVoice2\CosyVoice
python_env:
  type: embedded_python
  executable: E:\AiModel\tts\CosyVoice2\CosyVoice\py311\python.exe
launch:
  cwd: E:\AiModel\tts\CosyVoice2\CosyVoice
  command:
    - E:\AiModel\tts\CosyVoice2\CosyVoice\py311\python.exe
    - api.py
network:
  port: 5101
  healthcheck_url: http://127.0.0.1:5101/health
```

三模型建议：

- `CosyVoice`：优先走内嵌 Python 或后续切回 conda py310
- `F5-TTS`：优先走项目内 `python\py310\python.exe`
- `GPT-SoVITS`：优先走 `runtime\python.exe`

统一要求：

- 网关负责分配固定端口或从配置读取端口
- 各模型服务尽量改为支持显式 `--host` / `--port`
- 若现有脚本不支持，则薄改启动脚本或增加桥接启动文件

---

## 12. 参数映射原则

统一协议中的参数不能强制所有模型都完全支持。

建议规则：

- 通用参数尽量映射
- 不支持的参数忽略，不报错
- 模型私有参数进入 `parameters.extra`
- adapter 负责把统一参数翻译为模型原生请求

例如：

- `speed`：能映射就映射
- `pitch`：模型不支持则忽略
- `emotion`：优先转成参考音频或指令
- `instruction`：能支持 instruct 的模型再透传

这样协议更稳定，也不会被某一个模型绑架。

---

## 13. 错误处理

统一网关应屏蔽模型内部错误细节，统一返回标准错误码。

建议新增 provider 相关错误码：

- `PROVIDER_NOT_FOUND`
- `PROVIDER_DISABLED`
- `PROVIDER_START_TIMEOUT`
- `PROVIDER_UNAVAILABLE`
- `PROVIDER_HEALTHCHECK_FAILED`
- `PROVIDER_BAD_RESPONSE`

同时保留协议文档中的业务错误码：

- `INVALID_REQUEST`
- `VOICE_NOT_FOUND`
- `TEXT_TOO_LONG`
- `UNSUPPORTED_FORMAT`
- `SYNTHESIS_FAILED`
- `INTERNAL_ERROR`

---

## 14. 第一阶段实施建议

### 阶段 1：统一网关最小闭环

目标：

- 网关进程可以独立启动
- 能注册三模型
- 能自动启动模型
- 能请求 `/voices` 和 `/synthesize`

交付：

- provider 配置文件
- 进程管理器
- 3 个 adapter
- `/v1/providers`
- `/v1/providers/{provider_id}/health`
- `/v1/providers/{provider_id}/voices`
- `/v1/providers/{provider_id}/synthesize`

### 阶段 2：增强能力

目标：

- 支持 multipart 参考音频
- 返回更稳定的 voices 列表
- 增加缓存、预热、超时控制

### 阶段 3：高级能力

目标：

- GPT-SoVITS 的 clone
- CosyVoice 流式
- 模型实例池
- 并发队列和资源占用管理

---

## 15. 推荐技术路线

建议网关本身采用：

- Python 3.10
- FastAPI
- Pydantic
- httpx
- psutil
- uvicorn

原因：

- 适合快速搭 REST API
- 方便做 multipart
- 方便做进程管理与异步请求
- 作为“控制平面”足够轻，不要求与所有模型使用相同 Python 版本

注意：

- 网关不应直接依赖三个模型的 Python 包
- 网关与模型进程之间保持 HTTP 或子进程边界

---

## 16. 最终建议

最终建议是：

1. 保留现有 [docs\2026-04-02-bobogen-protocol-design.md](E:\AiModel\tts\docs\2026-04-02-bobogen-protocol-design.md) 作为协议规范
2. 新增独立 `bobogen-gateway` 工程作为统一入口
3. 第一阶段不改造模型核心，只包一层 adapter + process manager
4. 统一通过 `provider_id` 路由到具体模型实例
5. 未来新增模型时，优先新增配置和 adapter，而不是修改协议

这条路线最稳，也最符合你“快速启动模型和服务，供其它服务复用，并且后续可扩展其他模型”的目标。

---

## 17. 后续实现顺序

建议实现顺序如下：

1. 搭建 `bobogen-gateway` 空工程
2. 定义 provider 配置格式
3. 实现进程管理器
4. 实现 `CosyVoice` adapter
5. 实现 `F5-TTS` adapter
6. 实现 `GPT-SoVITS` adapter
7. 打通 `/providers`、`/voices`、`/synthesize`
8. 再补 `clone` 和 `stream`

这个顺序能最快形成可用闭环。

---

## 18. FastAPI 网关工程拆分

建议新增独立工程目录：

```text
bobogen-gateway\
  app\
    main.py
    config.py
    dependencies.py
    schemas\
      common.py
      provider.py
      synthesize.py
      voice.py
      error.py
    routers\
      providers.py
      synthesize.py
      health.py
      internal.py
    services\
      provider_registry.py
      process_manager.py
      audio_service.py
      health_service.py
    adapters\
      base.py
      cosyvoice.py
      f5tts.py
      gptsovits.py
    core\
      exceptions.py
      logging.py
      state.py
    utils\
      process.py
      http.py
  configs\
    gateway.yaml
    providers\
      cosyvoice-default.yaml
      f5tts-default.yaml
      gptsovits-default.yaml
  tests\
```

模块职责：

- `routers`：只负责 HTTP 路由和参数接收
- `schemas`：只负责统一协议的数据结构
- `services`：负责编排流程
- `adapters`：负责翻译模型差异
- `configs`：驱动 provider 注册和启动

FastAPI 只做“统一入口”，不直接承载模型推理逻辑。

---

## 19. 核心类设计

### 19.1 ProviderRegistry

职责：

- 扫描 `configs/providers/*.yaml`
- 解析 provider 配置
- 提供按 `provider_id` 查询
- 为每个 provider 选择对应 adapter

推荐接口：

```python
class ProviderRegistry:
    def list_providers(self) -> list[ProviderConfig]: ...
    def get_provider(self, provider_id: str) -> ProviderConfig: ...
    def get_adapter(self, provider_id: str) -> BaseProviderAdapter: ...
```

`ProviderRegistry` 只处理“配置与注册”，不处理启动状态。

### 19.2 ProcessManager

职责：

- 启动 provider 子进程
- 停止 provider 子进程
- 轮询健康检查
- 维护状态机
- 防止重复启动
- 在异常时返回明确错误

推荐接口：

```python
class ProcessManager:
    async def ensure_started(self, provider_id: str) -> ProviderRuntimeState: ...
    async def start(self, provider_id: str) -> ProviderRuntimeState: ...
    async def stop(self, provider_id: str) -> None: ...
    async def restart(self, provider_id: str) -> ProviderRuntimeState: ...
    async def healthcheck(self, provider_id: str) -> ProviderHealthResult: ...
    def get_state(self, provider_id: str) -> ProviderRuntimeState: ...
    def list_states(self) -> list[ProviderRuntimeState]: ...
```

### 19.3 BaseProviderAdapter

职责：

- 将统一协议翻译为模型原生接口
- 解析模型原生响应
- 把模型原生错误转成统一错误

推荐接口：

```python
class BaseProviderAdapter(Protocol):
    async def list_voices(self, provider: ProviderConfig) -> VoicesResponse: ...
    async def synthesize(
        self,
        provider: ProviderConfig,
        request: UnifiedSynthesizeRequest,
        files: UnifiedReferenceFiles | None = None,
    ) -> AudioResult: ...
    async def healthcheck(self, provider: ProviderConfig) -> HealthResult: ...
```

### 19.4 AudioService

职责：

- 接收 adapter 返回的音频结果
- 统一封装为 HTTP 音频响应
- 写标准响应头

推荐输出结构：

```python
@dataclass
class AudioResult:
    content: bytes
    content_type: str
    duration_seconds: float | None = None
    sample_rate: int | None = None
    format: str | None = None
```

---

## 20. ProcessManager 运行状态设计

### 20.1 状态机

建议使用以下状态：

- `stopped`
- `starting`
- `healthy`
- `unhealthy`
- `failed`

状态流转：

```text
stopped -> starting -> healthy
starting -> failed
healthy -> unhealthy -> healthy
healthy -> stopped
unhealthy -> failed
```

### 20.2 运行态对象

推荐结构：

```python
@dataclass
class ProviderRuntimeState:
    provider_id: str
    status: str
    pid: int | None
    port: int
    started_at: datetime | None
    last_health_at: datetime | None
    last_used_at: datetime | None
    last_error: str | None
    startup_attempts: int
```

### 20.3 必要机制

- 为每个 provider 保留一个启动锁，防止并发重复拉起
- 启动成功必须同时满足：
  - 子进程仍然存活
  - HTTP 健康检查通过
- 不只看 PID，不只看端口打开

---

## 21. 启动与请求时序

以 `POST /v1/providers/f5tts-default/synthesize` 为例：

1. 网关收到请求
2. 校验统一请求体
3. 通过 `ProviderRegistry` 找到 `f5tts-default`
4. 调用 `ProcessManager.ensure_started("f5tts-default")`
5. 若状态是 `stopped`，则启动子进程
6. `ProcessManager` 每隔固定间隔轮询目标 `healthcheck_url`
7. 健康检查通过后标记为 `healthy`
8. 调用 `F5TTSAdapter.synthesize()`
9. adapter 将统一参数翻译为底层接口参数
10. 拿到底层音频结果后转成统一 `AudioResult`
11. FastAPI 返回音频二进制流

如果第 6 步超时：

- 状态置为 `failed`
- 返回 `PROVIDER_START_TIMEOUT`

如果第 8 步底层接口报错：

- adapter 将异常翻译为统一错误
- 返回 `SYNTHESIS_FAILED` 或更具体错误码

---

## 22. 路由设计建议

### 22.1 对外接口

推荐对外暴露：

- `GET /v1/health`
- `GET /v1/providers`
- `GET /v1/providers/{provider_id}`
- `GET /v1/providers/{provider_id}/health`
- `GET /v1/providers/{provider_id}/voices`
- `POST /v1/providers/{provider_id}/synthesize`

兼容模式可保留：

- `GET /v1/voices?provider_id=...`
- `POST /v1/synthesize`

但主路径建议始终显式带 `provider_id`。

### 22.2 内部管理接口

建议增加：

- `GET /internal/providers/status`
- `POST /internal/providers/{provider_id}/start`
- `POST /internal/providers/{provider_id}/stop`
- `POST /internal/providers/{provider_id}/restart`

这些接口主要用于：

- 调试
- 运维
- 查看当前进程状态
- 手动重启某个 provider

---

## 23. 配置驱动启动

### 23.1 配置样例

建议每个 provider 一份配置文件，例如：

```yaml
provider_id: f5tts-default
provider_type: f5-tts
display_name: F5-TTS Default
enabled: true

runtime:
  root_dir: E:\AiModel\tts\F5-TTS
  cwd: E:\AiModel\tts\F5-TTS
  command:
    - E:\AiModel\tts\F5-TTS\python\py310\python.exe
    - api.py
  env:
    TTS_PORT: "5102"
  startup_timeout_ms: 90000
  request_timeout_ms: 180000
  idle_shutdown_seconds: 0

network:
  host: 127.0.0.1
  port: 5102
  base_url: http://127.0.0.1:5102
  healthcheck_path: /health

capabilities:
  voices: true
  synthesize: true
  clone: false
  stream: false

mapping:
  supports_reference_audio: true
  supports_instruction: false
  supports_speed: true
```

### 23.2 为什么优先不用 bat

程序化进程管理建议尽量直接执行：

- `python.exe api.py`

而不是优先执行：

- `run-api.bat`

原因：

- 更容易获得 PID
- 更容易收集 stdout/stderr
- 更容易判断退出码
- 更容易控制端口与环境变量

`.bat` 可以保留为人工启动入口，但不应成为网关主启动方式。

---

## 24. 健康检查策略

建议分两层：

### 24.1 进程层健康

- 子进程是否仍在运行
- 是否异常退出

### 24.2 HTTP 层健康

- `GET /health`
- 或底层轻量探测接口

推荐第一版给三个模型都补一个轻量 `/health`。

启动成功判定必须以 HTTP 层健康为准，不能只看进程存活。

---

## 25. 统一错误模型

推荐所有错误统一为：

```json
{
  "error": {
    "code": "PROVIDER_START_TIMEOUT",
    "message": "Provider f5tts-default failed to become healthy within 90000 ms",
    "details": {
      "provider_id": "f5tts-default"
    }
  }
}
```

新增 provider 级错误码：

- `PROVIDER_NOT_FOUND`
- `PROVIDER_DISABLED`
- `PROVIDER_START_TIMEOUT`
- `PROVIDER_UNAVAILABLE`
- `PROVIDER_HEALTHCHECK_FAILED`
- `PROVIDER_BAD_RESPONSE`

保留协议层错误码：

- `INVALID_REQUEST`
- `VOICE_NOT_FOUND`
- `TEXT_TOO_LONG`
- `UNSUPPORTED_FORMAT`
- `SYNTHESIS_FAILED`
- `INTERNAL_ERROR`

---

## 26. 日志与可观测性

建议至少区分三类日志：

- `gateway.access`
  - 请求入口、provider、耗时、状态码
- `gateway.process`
  - 启动、停止、重启、探活、超时
- `gateway.adapter`
  - 参数映射、底层响应、错误转换

推荐每条日志都带：

- `provider_id`
- `provider_type`
- `request_id`
- `latency_ms`
- `status`

内部状态接口 `GET /internal/providers/status` 建议返回：

- `provider_id`
- `status`
- `pid`
- `port`
- `started_at`
- `last_health_at`
- `last_used_at`
- `startup_attempts`
- `last_error`

---

## 27. 第一版落地边界

第一版必须完成：

- 配置注册三模型
- 自动拉起 provider
- 健康检查与失败返回
- `voices` 调用链路
- `synthesize` 调用链路
- 统一错误模型

第一版暂不追求：

- clone
- 流式输出
- 训练管理
- 自动扫描全部权重
- 复杂显存调度

只要第一版实现了“其它服务可以稳定通过统一 HTTP 调这三个模型”，目标就已经达成。
