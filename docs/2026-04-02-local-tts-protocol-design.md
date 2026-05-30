# Local TTS Protocol 设计文档

> **日期**: 2026-04-02
> **状态**: 设计中
> **目标**: 定义一套通用 TTS HTTP 协议规范，用于接入本地 TTS 模型服务

---

## 1. 背景与目标

### 1.1 问题

当前项目已有 4 个云端 TTS 适配器（EdgeTTS / BrowserSpeech / MiniMax / Bailian），但本地模型（GPT-SoVITS、CosyVoice、ChatTTS 等）的接入方式尚未标准化。

项目内存在两套协议定义：
- **TTSEngineAdapter** — 适配器层接口，所有云端适配器已实现
- **TPP v1 (TtsProviderProtocol)** — 供应商协议层，已定义但适配器未实现

两套协议职责不同，是上下层关系，不是重复。

### 1.2 目标

1. 定义一套 **Local TTS Protocol** OpenAPI 规范，本地模型按规范暴露 HTTP API
2. 在项目内实现 **LocalTTSAdapter**，作为 TTSEngineAdapter 的统一实现接入所有合规的本地模型
3. 补全 TtsProviderProtocol 上层能力声明，与应用侧配置对接
4. 实现进程管理器，消除用户手动启动模型服务的步骤

### 1.3 设计原则

- **模型服务只负责暴露端点**，不负责声明能力
- **应用侧通过配置决定能力**，UI 和参数面板据此渲染
- **必选端点只有两个**：语音合成 + 音色列表
- **可选端点**：克隆、设计、流式，模型实现了就配，没实现就不配
- **情绪控制是应用侧配置**，模型内部怎么实现（参考音频/参数/指令）由适配器翻译
- **一个 LocalTTSAdapter 类适配所有本地模型**，差异通过配置解决

---

## 2. 三层架构

```
┌─────────────────────────────────────────────┐
│          应用侧（配置 + UI）                   │
│  能力配置决定：情绪交互方式 / 端点可用性 / 参数  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│      适配器层（LocalTTSAdapter）               │
│  实现 TTSEngineAdapter + TtsProviderProtocol │
│  将应用侧意图翻译为 HTTP 请求                  │
│  每个本地模型实例一个 adapter（按 providerId）  │
└──────────────────┬──────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────┐
│      模型服务（实现 Local TTS Protocol）       │
│  暴露 RESTful HTTP 端点                       │
│  必选：合成 / 音色列表                         │
│  可选：克隆 / 设计 / 流式                      │
└─────────────────────────────────────────────┘
```

---

## 3. OpenAPI 规范

### 3.1 API 路径总览

| 方法 | 路径 | 必选 | 说明 |
|---|---|---|---|
| `GET` | `/v1/voices` | **必选** | 获取音色列表 |
| `POST` | `/v1/synthesize` | **必选** | 语音合成（非流式） |
| `POST` | `/v1/synthesize/stream` | 可选 | 流式语音合成 |
| `POST` | `/v1/clone` | 可选 | 克隆音色（同步或异步） |
| `GET` | `/v1/clone/{voice_id}/status` | 可选 | 异步克隆状态查询 |
| `POST` | `/v1/design` | 可选 | 设计音色 |
| `GET` | `/v1/health` | 推荐 | 健康检查 |

### 3.2 认证

如果配置了 `apiKey`，所有请求通过 HTTP Header 传递：

```
Authorization: Bearer <apiKey>
```

### 3.2 GET /v1/voices

获取模型支持的音色列表。

**请求**：

```
GET /v1/voices?language=zh HTTP/1.1
Accept: application/json
```

| 参数 | 位置 | 类型 | 必选 | 说明 |
|---|---|---|---|---|
| `language` | query | string | 否 | 按语言筛选（BCP 47） |
| `page` | query | integer | 否 | 页码，默认 1 |
| `page_size` | query | integer | 否 | 每页数量，默认 100 |

**响应**：

```json
{
  "voices": [
    {
      "voice_id": "character_happy",
      "name": "角色-开心",
      "language": ["zh", "en"],
      "gender": "female",
      "description": "温柔女声，适合旁白",
      "tags": ["温柔", "旁白", "女声"],
      "metadata": {}
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 100
}
```

**Voice 对象字段**：

| 字段 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `voice_id` | string | 是 | 音色唯一标识，合成时使用 |
| `name` | string | 是 | 音色显示名称 |
| `language` | string[] | 否 | 支持的语言列表 |
| `gender` | string | 否 | `male` / `female` / `neutral` |
| `description` | string | 否 | 音色描述 |
| `tags` | string[] | 否 | 标签（用于筛选和搜索） |
| `metadata` | object | 否 | 模型自定义扩展字段 |

### 3.3 POST /v1/synthesize

语音合成，返回音频二进制流。

支持两种请求格式：
- **JSON**（无参考音频时使用）
- **multipart/form-data**（携带参考音频时使用，避免大文件 base64 膨胀）

**JSON 请求**（无参考音频）：

```json
{
  "text": "你好，今天天气真好",
  "voice_id": "character_happy",
  "language": "zh",
  "parameters": {
    "speed": 1.0,
    "pitch": 0,
    "volume": 1.0,
    "emotion": "happy",
    "emotion_intensity": 0.8,
    "instruction": "用温柔的语气说",
    "extra": {}
  },
  "output": {
    "format": "wav",
    "sample_rate": 24000
  }
}
```

**multipart 请求**（携带参考音频）：

```
POST /v1/synthesize HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="request"

{"text":"你好","voice_id":"character_happy","parameters":{"speed":1.0},"output":{"format":"wav"}}
------Boundary
Content-Disposition: form-data; name="reference_audio"; filename="ref.wav"
Content-Type: audio/wav

<binary audio data>
------Boundary
Content-Disposition: form-data; name="reference_text"

这是参考音频对应的文本
------Boundary--
```

multipart 字段：

| 字段 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `request` | JSON string | **是** | 合成请求体（同上方 JSON 格式） |
| `reference_audio` | file | 否 | 参考音频文件 |
| `reference_text` | string | 否 | 参考音频对应文本 |

**请求体字段**：

| 字段 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `text` | string | **是** | 待合成文本 |
| `voice_id` | string | **是** | 音色 ID |
| `language` | string | 否 | 语言（BCP 47），不传则由模型推断 |
| `parameters` | object | 否 | 合成参数（见下表） |
| `output` | object | 否 | 输出格式控制（见下表） |

**parameters 对象**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `speed` | number | 语速倍率 0.5-2.0，默认 1.0 |
| `pitch` | number | 音调半音 -12 到 +12，默认 0 |
| `volume` | number | 音量 0.0-1.0，默认 1.0 |
| `emotion` | string | 情绪标签（happy/sad/angry/...），模型不支持的参数应忽略 |
| `emotion_intensity` | number | 情绪强度 0.0-1.0 |
| `instruction` | string | 自然语言演播指令 |
| `reference_audio` | string | 参考音频（base64 编码） |
| `reference_text` | string | 参考音频对应文本 |
| `extra` | object | 模型自定义扩展参数 |

**关于 reference_audio 的语义说明**：

`reference_audio` 有两种来源，适配器按以下优先级处理：
1. **情绪映射参考音频**：当情绪实现方式为 `reference_audio`，且当前请求携带了情绪标签，适配器根据 `emotionReferenceMap` 查找对应的参考音频
2. **用户指定参考音频**：用户在合成参数中主动指定的参考音频

两者冲突时，**情绪映射优先**（情绪映射是应用侧配置的稳定行为，用户指定是临时覆盖）。

**output 对象**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `format` | string | 输出格式：`wav` / `mp3` / `ogg` / `pcm` / `flac` |
| `sample_rate` | integer | 采样率（Hz） |

**成功响应**（二进制流）：

```
HTTP/1.1 200 OK
Content-Type: audio/wav
X-Audio-Duration: 3.52

<binary audio data>
```

| 响应头 | 说明 |
|---|---|
| `Content-Type` | 音频 MIME 类型 |
| `X-Audio-Duration` | 可选，音频时长（秒） |

**错误响应**：

```json
{
  "error": {
    "code": "TEXT_TOO_LONG",
    "message": "文本长度超过限制",
    "details": {}
  }
}
```

**错误码定义**：

| HTTP 状态码 | code | 说明 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 请求参数错误 |
| 400 | `TEXT_TOO_LONG` | 文本超出长度限制 |
| 400 | `UNSUPPORTED_FORMAT` | 不支持的输出格式 |
| 404 | `VOICE_NOT_FOUND` | 音色 ID 不存在 |
| 422 | `SYNTHESIS_FAILED` | 合成执行失败 |
| 500 | `INTERNAL_ERROR` | 模型内部错误 |

### 3.4 POST /v1/synthesize/stream

流式语音合成，返回 chunked 音频流。

**请求体**：与 `/v1/synthesize` 完全相同。

**成功响应**：

```
HTTP/1.1 200 OK
Content-Type: audio/pcm
Transfer-Encoding: chunked
X-Audio-Sample-Rate: 24000
X-Audio-Format: pcm_s16le

<chunked binary audio data>
```

模型不实现此端点返回 `404`。

### 3.5 POST /v1/clone

克隆音色，上传参考音频创建新音色。

支持同步和异步两种模式。模型根据自身能力选择：
- 同步：直接返回结果
- 异步：返回 `status: "processing"` + `task_id`，需轮询状态

**请求**：

```
POST /v1/clone HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary
```

| 字段 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `audio` | file | **是** | 参考音频文件（multipart） |
| `text` | string | 否 | 参考音频对应文本 |
| `name` | string | 否 | 新音色名称 |
| `language` | string | 否 | 参考音频语言 |
| `emotion` | string | 否 | 参考音频情绪标签（用于情绪-参考音频映射） |

**同步响应**（克隆秒级完成）：

```json
{
  "voice_id": "cloned_abc123",
  "name": "我的声音",
  "status": "ready"
}
```

**异步响应**（克隆需要训练时间）：

```json
{
  "task_id": "clone_task_001",
  "status": "processing",
  "estimated_seconds": 120
}
```

**异步状态查询**：`GET /v1/clone/{task_id}/status`

```json
{
  "task_id": "clone_task_001",
  "status": "ready",
  "voice_id": "cloned_abc123",
  "name": "我的声音"
}
```

**status 枚举**：`processing` / `ready` / `failed`

模型不实现此端点返回 `404`。

### 3.6 POST /v1/design

通过参数设计音色（调整音色特征创造新音色）。

**请求**：

```json
{
  "base_voice_id": "character_happy",
  "name": "自定义温柔女声",
  "parameters": {
    "extra": {}
  }
}
```

| 字段 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `base_voice_id` | string | 否 | 基于哪个音色调整 |
| `name` | string | 否 | 新音色名称 |
| `parameters` | object | 否 | 音色设计参数 |
| `parameters.extra` | object | 否 | 模型自定义设计参数，字段完全由模型定义 |

> **说明**：设计参数没有统一标准，不同模型的参数完全不同（如 GPT-SoVITS 和 CosyVoice 的音色调整维度差异很大）。
> 所有模型特有参数统一放 `extra` 中，应用侧通过 `synthesis.extraParameters` 配置来暴露 UI 表单。

**成功响应**：

```json
{
  "voice_id": "designed_xyz789",
  "name": "自定义温柔女声",
  "status": "ready"
}
```

模型不实现此端点返回 `404`。

### 3.7 GET /v1/health

健康检查。

**响应**：

```json
{
  "status": "ok",
  "model": "GPT-SoVITS",
  "version": "1.2.0"
}
```

---

## 4. 应用侧能力配置

### 4.1 配置模型

用户在管理页配置一个本地模型时，需要填写以下配置：

```typescript
interface LocalTTSProviderConfig {
  /** 基础连接 */
  connection: {
    name: string;                    // 显示名称，如 "我的 GPT-SoVITS"
    baseUrl: string;                 // 服务地址，如 http://localhost:9880
    apiKey?: string;                 // 可选认证密钥
    timeout?: number;                // 请求超时（毫秒），默认 30000
  };

  /** 进程管理（可选，启用后应用自动启停模型服务） */
  processManagement?: {
    enabled: boolean;
    startCommand: string;            // 启动命令，如 "python api_v2.py"
    workingDirectory: string;        // 工作目录，如 "D:\GPT-SoVITS\"
    environment?: Record<string, string>;
    startupTimeout: number;          // 启动等待超时（秒），默认 30
    readinessProbe: {
      path: string;                  // 默认 '/v1/health'
      expectedStatus: number;        // 默认 200
      intervalSeconds: number;       // 探测间隔，默认 2
      maxRetries: number;            // 最大重试次数，默认 15
    };
    shutdown: {
      autoStop: boolean;             // 应用关闭时是否自动停止
      stopSignal: 'SIGTERM' | 'SIGKILL' | 'taskkill';
      gracefulTimeout: number;       // 优雅关闭等待（毫秒），默认 5000
    };
  };

  /** 端点可用性 */
  endpoints: {
    synthesize: true;                // 必选
    voices: true;                    // 必选
    stream: boolean;
    clone: boolean;
    design: boolean;
  };

  /** 合成能力 */
  synthesis: {
    outputFormats: string[];         // ['wav', 'mp3', 'ogg']
    defaultFormat: string;           // 'wav'
    defaultSampleRate: number;       // 24000

    speed: boolean;
    pitch: boolean;
    volume: boolean;

    /** 情绪控制 */
    emotion: {
      enabled: boolean;
      mode: 'none' | 'selection' | 'instruct';
      availableEmotions?: string[];
      intensityControl: boolean;
      /**
       * 实现方式（适配器内部翻译逻辑）：
       * - 'parameter': 直接传 emotion 参数给模型
       * - 'reference_audio': 根据情绪切换不同参考音频文件
       * - 'instruction': 将情绪转换为自然语言指令
       */
      implementation: 'parameter' | 'reference_audio' | 'instruction';
      /**
       * 参考音频模式专用：情绪到参考音频的映射
       * key = emotion tag, value = 参考音频文件路径（项目本地路径）
       * 适配器在合成前自动读取文件并编码为 base64
       */
      emotionReferenceMap?: Record<string, string>;
    };

    instruction: boolean;
    referenceAudio: boolean;

    extraParameters?: Record<string, {
      type: 'string' | 'number' | 'boolean';
      label: string;
      default?: unknown;
      description?: string;
    }>;
  };

  /** 并发与限流 */
  rateLimit?: {
    /** 最大并发合成请求数，默认 1（本地模型通常单 GPU，一次只能处理一个） */
    maxConcurrency: number;
    /** 请求超时后的重试次数，默认 0 */
    retries: number;
    /** 重试间隔（毫秒），默认 1000 */
    retryDelay: number;
  };
}
```

### 4.2 配置 UI 示意

```
┌─ 本地模型配置 ──────────────────────────────────────┐
│                                                      │
│  基础信息                                            │
│  ├ 名称: [我的 GPT-SoVITS      ]                    │
│  ├ 地址: [http://localhost:9880 ]                    │
│  └ 超时: [30000] ms                                  │
│                                                      │
│  自动启动                                            │
│  ☑ 启用（应用管理模型服务的启停）                     │
│  ├ 启动命令: [python api_v2.py             ]         │
│  ├ 工作目录: [D:\GPT-SoVITS\              ]         │
│  ├ 就绪检测: GET /v1/health                          │
│  ├ 启动等待: [30] 秒                                 │
│  └ ☑ 关闭应用时自动停止服务                          │
│                                                      │
│  端点                                                │
│  ├ ☑ 合成（必选）                                    │
│  ├ ☑ 音色列表（必选）                                │
│  ├ ☐ 流式合成                                        │
│  ├ ☑ 克隆                                            │
│  └ ☐ 设计                                            │
│                                                      │
│  合成能力                                            │
│  ├ 输出格式: [wav] [mp3] [ogg]                       │
│  ├ ☑ 语速  ☑ 音调  ☑ 音量                           │
│  ├ 情绪控制:                                         │
│  │  ├ 交互方式: ● 情绪选择 ○ 指令 ○ 不支持           │
│  │  ├ 情绪强度: ☑ 支持                               │
│  │  ├ 实现方式: ● 参考音频 ○ 参数 ○ 指令转换         │
│  │  └ 情绪映射:                                      │
│  │     neutral → [选择文件] neutral_ref.wav           │
│  │     happy   → [选择文件] happy_ref.wav             │
│  │     sad     → [选择文件] sad_ref.wav               │
│  │     angry   → [选择文件] angry_ref.wav             │
│  ├ ☑ 参考音频                                        │
│  └ ☐ 指令控制                                        │
│                                                      │
│  [测试连接]  [保存]                                   │
└──────────────────────────────────────────────────────┘
```

---

## 5. 适配器层设计

### 5.1 LocalTTSAdapter

位于 `src/main/services/voice/adapters/LocalTTSAdapter.ts`。

核心职责：
- 读取 `LocalTTSProviderConfig` 配置
- 将 `TTSRequest` 翻译为 Local TTS Protocol HTTP 请求
- 处理情绪翻译逻辑（根据 `emotion.implementation` 配置）
- 处理二进制音频响应，写入文件

**多实例支持**：每个本地模型 provider 对应一个 `LocalTTSAdapter` 实例，
通过 `providerId` 区分。注册到 `AdapterRegistry` 时使用 `local_${providerId}` 作为 key。

```typescript
class LocalTTSAdapter implements TTSEngineAdapter {
  readonly engineType: TTSEngineType = 'local';
  readonly engineName: string;

  private config: LocalTTSProviderConfig;

  constructor(private providerId: string, config: LocalTTSProviderConfig) { ... }

  async textToSpeech(request: TTSRequest, outputPath: string): Promise<TTSResponse> {
    // 1. 构建协议请求体
    const body = this.buildSynthesizeRequest(request);

    // 2. 情绪翻译
    this.applyEmotionTranslation(body, request);

    // 3. 发送 HTTP 请求
    const response = await fetch(`${this.config.connection.baseUrl}/v1/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    // 4. 处理错误
    if (!response.ok) { /* 解析错误 JSON */ }

    // 5. 写入音频文件
    const buffer = Buffer.from(await response.arrayBuffer());
    await writeFile(outputPath, buffer);

    // 6. 提取元数据
    const duration = response.headers.get('X-Audio-Duration');

    return { success: true, outputFile: outputPath, duration, ... };
  }

  async listVoices(language?: string): Promise<EngineVoice[]> { ... }
  async healthCheck(): Promise<EngineHealthStatus> { ... }

  /** 克隆音色（需要 TTSEngineAdapter 接口扩展） */
  async cloneVoice(audio: Buffer, options?: CloneOptions): Promise<CloneResult> { ... }

  /** 设计音色（需要 TTSEngineAdapter 接口扩展） */
  async designVoice(params: DesignParams): Promise<DesignResult> { ... }
}
```

### 5.2 情绪翻译逻辑

适配器内部根据配置的 `emotion.implementation` 决定如何翻译情绪：

```typescript
private applyEmotionTranslation(body: SynthesizeRequest, request: TTSRequest): void {
  const { emotion } = this.config.synthesis;
  if (!emotion.enabled || !request.emotion) return;

  switch (emotion.implementation) {
    case 'parameter':
      // 直接传 emotion 参数
      body.parameters.emotion = request.emotion;
      if (request.emotionIntensity) {
        body.parameters.emotion_intensity = request.emotionIntensity;
      }
      break;

    case 'reference_audio':
      // 根据情绪映射表切换参考音频
      const refAudioPath = emotion.emotionReferenceMap?.[request.emotion];
      if (refAudioPath) {
        // 读取文件并编码为 base64
        const audioBuffer = await readFile(refAudioPath);
        body.parameters.reference_audio = audioBuffer.toString('base64');
      }
      break;

    case 'instruction':
      // 将情绪转换为自然语言指令
      body.parameters.instruction = `用${request.emotion}的语气说`;
      if (request.emotionIntensity) {
        body.parameters.instruction += `，强度${Math.round(request.emotionIntensity * 100)}%`;
      }
      break;
  }
}
```

### 5.3 TTSEngineAdapter 接口扩展

当前接口缺少 `clone` 和 `design` 方法，需要扩展：

```typescript
interface TTSEngineAdapter {
  // ... 现有方法 ...

  /** 克隆音色（可选实现） */
  cloneVoice?(audio: Buffer, options?: CloneOptions): Promise<CloneResult>;

  /** 设计音色（可选实现） */
  designVoice?(params: DesignParams): Promise<DesignResult>;
}
```

使用可选方法，不破坏现有适配器。

---

## 6. 进程管理器

### 6.1 设计目标

消除"用户手动启动模型服务"这一步。用户配置好启动命令后，应用自动管理模型服务的生命周期。

### 6.2 核心流程

```
应用启动
  → 遍历所有已配置的本地模型
  → 对启用了自动启动的模型：
    1. spawn 子进程（startCommand, cwd, env）
    2. 轮询 readinessProbe（GET /v1/health），直到返回 200
    3. 超时则标记为"启动失败"，UI 提示用户

用户使用 TTS
  → 检查服务状态
  → 在线 → 正常调用
  → 离线 → 自动重启或提示用户

应用关闭
  → 对 autoStop=true 的服务发送 SIGTERM
  → 等待 gracefulTimeout
  → 仍未退出则 SIGKILL / taskkill
```

### 6.3 LocalModelProcessManager

位于 `src/main/services/voice/LocalModelProcessManager.ts`。

```typescript
class LocalModelProcessManager {
  private processes: Map<string, ManagedProcess> = new Map();

  async start(providerId: string, config: ProcessManagementConfig): Promise<void> {
    // 1. 检测端口是否已被占用（避免冲突）
    const port = extractPort(config.readinessProbe.path);
    if (await isPortInUse(port)) {
      throw new Error(`端口 ${port} 已被占用`);
    }

    // 2. spawn 子进程
    const child = spawn(config.startCommand, {
      cwd: config.workingDirectory,
      env: { ...process.env, ...config.environment },
      shell: true,
      detached: false,
    });

    // 3. 等待就绪
    await this.waitForReady(config.readinessProbe, config.startupTimeout);

    this.processes.set(providerId, { child, config, status: 'running' });
  }

  async stop(providerId: string): Promise<void> {
    const managed = this.processes.get(providerId);
    if (!managed) return;

    const { child, config } = managed;
    child.kill(config.shutdown.stopSignal);

    await Promise.race([
      once(child, 'exit'),
      setTimeout(config.shutdown.gracefulTimeout),
    ]);

    if (child.exitCode === null) {
      child.kill('SIGKILL');
    }

    this.processes.delete(providerId);
  }

  getStatus(providerId: string): 'running' | 'stopped' | 'starting' | 'error' { ... }

  async stopAll(): Promise<void> { ... }
}
```

### 6.4 生命周期集成

```typescript
// main/index.ts
const processManager = new LocalModelProcessManager();

app.on('ready', async () => {
  const localProviders = await loadLocalProviders();
  for (const provider of localProviders) {
    if (provider.processManagement?.enabled) {
      await processManager.start(provider.id, provider.processManagement);
    }
  }
});

app.on('before-quit', async () => {
  await processManager.stopAll();
});
```

### 6.5 UI 状态展示

```
┌─ 本地模型 ──────────────────────────────────────┐
│                                                   │
│  🟢 我的 GPT-SoVITS        [停止] [配置]         │
│     http://localhost:9880                          │
│     自动启动 · 运行中 2分15秒                      │
│                                                   │
│  🔴 CosyVoice 本地          [启动] [配置]         │
│     http://localhost:50000                         │
│     自动启动 · 已停止                              │
│                                                   │
│  [+ 添加本地模型]                                  │
└───────────────────────────────────────────────────┘
```

---

## 7. 与现有架构的集成

### 7.1 多实例注册

当前 `AdapterRegistry` 用 `Map<TTSEngineType, TTSEngineAdapter>` 存储，一个 key 只能存一个适配器。
多个本地模型实例需要共存。

**方案**：注册时使用 `local_${providerId}` 作为 key，保持 engineType 为 `'local'` 不变。

```typescript
// 注册
adapterRegistry.register(`local_${providerId}`, adapter);

// 使用时通过 voice 的 providerId 查找
const adapterKey = `local_${voice.providerId}`;
const adapter = adapterRegistry.get(adapterKey);
```

### 7.2 Provider 系统集成

本地模型作为新的 Provider 类型接入现有 Provider-Model-Voice 体系：

- `providers` 表：`provider_type = 'local'`
- `provider_configs` 表：存储 `LocalTTSProviderConfig` JSON
- `provider_capabilities` 表：`capability_type = 'tts'`
- `models` 表：可选，如果模型有多个模型变体
- `voices` 表：通过 `GET /v1/voices` 同步到本地
  **音色 ID 稳定性策略**：同步时以 `voice_id` + `name` 为匹配键（而非仅靠 `voice_id`），以避免本地模型重启后 voice_id 变化导致映射失效。### 7.3 TTSAssetProviderKey 扩展

```typescript
export type TTSAssetProviderKey =
  | 'bailian'
  | 'minimax'
  | 'edge_tts'
  | 'browser_speech'
  | 'local';  // 新增
```

### 7.4 TTSEngineType 扩展

```typescript
export type TTSEngineType =
  | ... // 现有类型
  | 'local';  // 通用本地模型（替代原来的 custom）
```

---

## 8. 数据流

### 8.1 合成流程

```
用户点击合成
  → DialogueAudioService.getOrCreateDialogueAudio()
    → TTSEngineDomain.synthesize()
      → resolveParameters()（台词+角色参数合并）
      → callTTSEngine()
        → VoiceRepository 查音色（获取 providerId）
        → voiceReuseResolverService 解析复用句柄
        → adapterRegistry.get(`local_${providerId}`) 获取对应 adapter
        → adapter.textToSpeech()
          → buildSynthesizeRequest()（构建协议请求）
          → applyEmotionTranslation()（情绪翻译：参数/参考音频/指令）
          → POST /v1/synthesize（HTTP 请求）
          → 写入音频文件
          → 解析时长
        → 返回 TTSResponse
```

### 8.2 音色同步流程

```
管理页点击"同步音色"
  → voiceAPI.syncCloudVoices()
    → IPC → VoiceService
      → LocalTTSAdapter.listVoices()
        → GET /v1/voices
        → 映射为 EngineVoice[]
      → 写入 voices 表
```

**音色 ID 稳定性策略**：

本地模型每次启动可能返回不同的 `voice_id`，因此同步音色时需要考虑 ID 变化：

1. **匹配策略**：同步时优先以 `name`（音色名称）匹配已有记录，而非仅靠 `voice_id`
2. **ID 变更处理**：
   - 匹配到已有音色 → 保留本地 `id`，更新 `remote_id` 为新 `voice_id`
   - 未匹配到 → 创建新音色记录
   - 已有音色不再出现在同步结果中 → 标记为 `disabled`（不删除，避免引用断裂）
3. **同步频率建议**：本地模型音色变更不频繁，建议仅在用户主动触发或模型重启后手动同步

### 8.3 克隆流程

```
用户上传参考音频
  → voiceAPI.cloneVoice()
    → IPC → VoiceService
      → LocalTTSAdapter.cloneVoice()
        → POST /v1/clone（multipart）
        → 返回新 voice_id
      → 写入 voices 表
```

---

## 9. OpenAPI 规范文件

完整的 OpenAPI 3.0 规范将输出为 `docs/specs/local-tts-protocol.openapi.yaml`，
作为独立文件供本地模型开发者参考和实现。

---

## 10. 实施阶段

### Phase 1：协议规范 + 基础适配器

- [ ] 输出 OpenAPI 3.0 YAML 规范文件
- [ ] 实现 `LocalTTSProviderConfig` 类型定义
- [ ] 扩展 `TTSEngineAdapter` 接口（添加可选 clone/design 方法）
- [ ] 实现 `LocalTTSAdapter`（合成 + 音色列表 + 健康检查）
- [ ] 注册到适配器注册表（支持多实例）
- [ ] Provider 系统集成（数据库表 + IPC）

### Phase 2：进程管理器

- [ ] 实现 `LocalModelProcessManager`（spawn / readinessProbe / graceful stop / 端口冲突检测）
- [ ] 应用生命周期集成（启动时自动拉起、退出时自动停止）
- [ ] 进程状态 UI 展示（运行中 / 已停止 / 启动失败）
- [ ] 手动启停按钮

### Phase 3：能力配置 UI + 情绪翻译

- [ ] 管理页本地模型配置表单
- [ ] 情绪翻译逻辑（三种实现方式）
- [ ] 情绪参考音频映射管理
- [ ] 音色同步功能

### Phase 4：高级功能

- [ ] 流式合成支持
- [ ] 克隆端点对接
- [ ] 设计端点对接
- [ ] 自定义扩展参数支持

---

## 11. 文件清单（新增/修改）

| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/specs/local-tts-protocol.openapi.yaml` | 新增 | OpenAPI 规范 |
| `src/shared/types/local-tts-protocol.ts` | 新增 | 协议类型定义 |
| `src/shared/types/local-tts-provider-config.ts` | 新增 | 应用侧配置类型 |
| `src/main/services/voice/adapters/LocalTTSAdapter.ts` | 新增 | 通用本地模型适配器 |
| `src/main/services/voice/adapters/ttsEngineAdapter.ts` | 修改 | 扩展 clone/design 可选方法 |
| `src/main/services/voice/adapters/index.ts` | 修改 | 注册本地适配器（多实例支持） |
| `src/main/services/voice/LocalModelProcessManager.ts` | 新增 | 进程管理器 |
| `src/shared/types/ttsAssetProvider.ts` | 修改 | 扩展 TTSAssetProviderKey |
| `src/shared/types/voice.ts` | 修改 | TTSEngineType 新增 'local' |
| `src/main/index.ts` | 修改 | 应用生命周期集成进程管理 |
| `src/renderer/src/pages/manage/tabs/` | 新增 | 本地模型配置 UI |

---

_最后更新: 2026-04-02_
