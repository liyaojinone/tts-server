# BoboGen API Reference

> 更新时间：2026-06-01
> Gateway `:6006`

客户端只需配置一个 `baseUrl`：

```
http://127.0.0.1:6006/local_index_tts
```

所有接口都在 `/{provider_id}/v1/*` 下，也可通过 `/v1/*` 直接访问（不限定 provider）。

新一代统一生成协议直接使用 Gateway 根路径：

```
http://127.0.0.1:6006/v1/generate
```

## Provider ID

| Provider ID | 引擎 | 端口 |
|-------------|------|------|
| `local_index_tts` | IndexTTS2 | 5104 |
| `local_voxcpm` | VoxCPM2 | 5105 |
| `local_gpt_sovits` | GPT-SoVITS | 5103 |
| `local_f5_tts` | F5-TTS | 5102 |
| `local_cosyvoice2` | CosyVoice2 | 5101 |
| `stable_audio_3_small_sfx` | Stable Audio 3 Small-SFX | 5106 |
| `qwen3_asr_0_6b` | Qwen3-ASR 0.6B | 5110 |
| `qwen3_asr_1_7b` | Qwen3-ASR 1.7B | 5111 |
| `qwen3_forced_aligner_0_6b` | Qwen3 ForcedAligner 0.6B | 5112 |
| `campplus_speaker_diarization` | CAM++ Speaker Diarization | 5113 |

## Authentication

设置 `BOBOGEN_API_KEY` 后需带 `Authorization: Bearer <key>`。

---

## OpenAPI / Postman / Apifox

Gateway 默认暴露机器可读 OpenAPI：

```text
http://127.0.0.1:6006/openapi.json
http://127.0.0.1:6006/docs
http://127.0.0.1:6006/redoc
```

Postman 或 Apifox 可直接导入 `http://127.0.0.1:6006/openapi.json`。导入后会按接口标签区分：

| 分类 | 说明 |
|------|------|
| `00 Health` | Gateway 健康检查与日志 |
| `01 Models` | 模型列表、模型详情和动态参数 schema |
| `02 Generate 新统一接口` | 推荐使用的统一生成入口 |
| `03 Provider 管理` | Provider 状态、启动、停止、重启、日志 |
| `04 Legacy Provider 旧接口` | 旧客户端兼容接口 |
| `05 Stable Audio 3 调参` | Stable Audio 3 参数说明入口 |

`/v1/generate` 的 `input` 和 `parameters` 是动态 dict，不同模型不同。不要手猜参数；先请求 `/v1/models/{model_id}`，读取返回的 `input_schema`、`parameters_schema`、`output_schema` 和 `examples`。生成接口返回 WAV 二进制音频，在 Postman 中建议使用 **Send and Download**，或保存响应到 `.wav` 文件后试听。

---

## 统一生成 API

旧 TTS 专用接口暂时保留；新接入优先使用统一生成协议。

### 模型列表 `GET /v1/models`

```bash
curl http://127.0.0.1:6006/v1/models
```

响应：

```json
{
  "models": [
    {
      "id": "local_f5_tts",
      "name": "F5-TTS",
      "provider_id": "local_f5_tts",
      "tasks": ["tts.speech"],
      "outputs": ["audio/wav"],
      "enabled": true
    }
  ]
}
```

### 模型详情 `GET /v1/models/{model_id}`

返回模型任务、输出格式、默认音色、能力字段，以及动态参数定义：

| 字段 | 说明 |
|------|------|
| `input_schema` | `input` dict 的 JSON Schema |
| `parameters_schema` | `parameters` dict 的 JSON Schema |
| `output_schema` | `output` 选项 JSON Schema |
| `examples` | 可直接复制到 `/v1/generate` 的请求示例 |

当前 TTS provider 会从旧 provider 配置自动推导 `tts.speech`。Stable Audio 3 会返回 `prompt`、`duration`、`steps`、`cfg_scale`、`seed`、`batch_size` 等调参字段。

### 生成 `POST /v1/generate`

**JSON**：

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/v1/generate \
  -d '{
    "model": "local_f5_tts",
    "task": "tts.speech",
    "input": {
      "text": "你好。",
      "voice": "f5-default",
      "language": "zh"
    },
    "parameters": {
      "reference_audio": {"kind": "path", "path": "/home/test.wav"},
      "reference_text": "参考文本",
      "speed": 1.0
    },
    "output": {"format": "wav", "sample_rate": 24000}
  }'
```

**multipart**：

```bash
curl -sS -o out.wav \
  -X POST http://127.0.0.1:6006/v1/generate \
  -F 'request={"model":"local_f5_tts","task":"tts.speech","input":{"text":"你好","voice":"f5-default"},"parameters":{"reference_audio":{"kind":"upload","field":"ref_audio"}}}' \
  -F "ref_audio=@speaker.wav"
```

`FileInput` 支持三种来源：

| kind | 示例 | 说明 |
|------|------|------|
| `upload` | `{"kind":"upload","field":"ref_audio"}` | multipart 上传字段 |
| `path` | `{"kind":"path","path":"/home/test.wav"}` | 服务器本地文件 |
| `data_uri` | `{"kind":"data_uri","data":"data:audio/wav;base64,..."}` | JSON 内联 base64 |

响应为二进制音频流，包含：

| Header | 说明 |
|--------|------|
| `X-Provider-Id` | 实际处理请求的 provider ID |
| `X-Model-Id` | 请求中的统一模型 ID |
| `X-Task` | 请求任务类型 |
| `X-Audio-Duration` | 音频时长（秒），下游提供时返回 |
| `X-Sample-Rate` | 采样率（Hz），下游提供时返回 |

错误：

```json
{"error": {"code": "MODEL_NOT_FOUND", "message": "...", "details": {}}}
```

常见错误码：`MODEL_NOT_FOUND`、`UNSUPPORTED_TASK`、`INVALID_REQUEST`。

### Stable Audio 3 Small-SFX

Stable Audio 3 通过统一生成协议接入，模型 ID 为 `stable_audio_3_small_sfx`，任务为 `audio.generate`。

```bash
curl -sS -H "Content-Type: application/json" -o sfx.wav \
  -X POST http://127.0.0.1:6006/v1/generate \
  -d '{
    "model": "stable_audio_3_small_sfx",
    "task": "audio.generate",
    "input": {
      "prompt": "short cinematic whoosh impact"
    },
    "parameters": {
      "duration": 7,
      "seed": 1234
    },
    "output": {"format": "wav", "sample_rate": 44100}
  }'
```

本地准备步骤：

```bash
git clone https://github.com/Stability-AI/stable-audio-3.git models/stable-audio-3/repo
cd models/stable-audio-3/repo
uv sync
huggingface-cli login
```

需要先在 Hugging Face 接受 `stabilityai/stable-audio-3-small-sfx` 模型条款。服务启动脚本默认读取 `models/stable-audio-3/repo/.venv`；如需使用其他 Python，设置 `STABLE_AUDIO3_PYTHON`。

---

### Qwen3-ASR

Qwen3-ASR 通过统一生成协议接入，默认本地模型 ID 为 `qwen3_asr_0_6b`，任务为 `asr.transcribe`，返回 JSON。

```bash
curl -sS -X POST http://127.0.0.1:6006/v1/generate \
  -F 'request={"model":"qwen3_asr_0_6b","task":"asr.transcribe","input":{"audio":{"kind":"upload","field":"audio"},"language":"auto"},"parameters":{"mode":"offline","timestamps":false},"output":{"format":"json"}}' \
  -F "audio=@speech.wav"
```

响应：

```json
{
  "text": "识别文本",
  "language": "Chinese",
  "duration_seconds": null,
  "segments": [],
  "model": "qwen3_asr_0_6b"
}
```

服务位于 `services/qwen3-asr-service`，必须使用 CUDA 版 PyTorch。0.6B 默认端口 `5110`；1.7B 预留端口 `5111`，可通过 provider `qwen3_asr_1_7b` 启动测试。

### Qwen3 ForcedAligner

Qwen3 ForcedAligner 通过统一生成协议接入，模型 ID 为 `qwen3_forced_aligner_0_6b`，任务为 `audio.align`。它不做语音识别，只负责把可信文本对齐到音频，返回片段内时间和工程全局时间。客户端仍负责 FFmpeg 静音检测、VAD 粗切、字幕 cue 拆分和编辑策略。

```bash
curl -sS -X POST http://127.0.0.1:6006/v1/generate \
  -F 'request={"model":"qwen3_forced_aligner_0_6b","task":"audio.align","input":{"audio":{"kind":"upload","field":"audio"},"text":"你终于来了。","language":"Chinese","clip_start":120.0},"parameters":{"granularity":"word"},"output":{"format":"json"}}' \
  -F "audio=@line.wav"
```

响应：

```json
{
  "text": "你终于来了。",
  "language": "Chinese",
  "clip_start": 120.0,
  "segments": [
    {
      "index": 0,
      "text": "你",
      "start": 0.1,
      "end": 0.22,
      "global_start": 120.1,
      "global_end": 120.22
    }
  ],
  "model": "qwen3_forced_aligner_0_6b"
}
```

---

### CAM++ Speaker Diarization

CAM++ Speaker Diarization 通过统一生成协议接入，模型 ID 为 `campplus_speaker_diarization`，任务为 `audio.diarize`。它只回答“谁在什么时候说话”，返回匿名 speaker 标签；不做语音识别，也不把 `SPEAKER_00` 自动映射成真实角色名。

```bash
curl -sS -X POST http://127.0.0.1:6006/v1/generate \
  -F 'request={"model":"campplus_speaker_diarization","task":"audio.diarize","input":{"audio":{"kind":"upload","field":"audio"},"clip_start":10.0},"parameters":{"oracle_num":2,"min_duration":0.0},"output":{"format":"json"}}' \
  -F "audio=@dialogue.wav"
```

响应：

```json
{
  "model": "campplus_speaker_diarization",
  "clip_start": 10.0,
  "segments": [
    {
      "index": 0,
      "speaker": "SPEAKER_00",
      "start": 0.12,
      "end": 3.84,
      "global_start": 10.12,
      "global_end": 13.84
    }
  ]
}
```

服务位于 `services/speaker-diarization-service`，默认端口 `5113`。已知说话人数时可传 `oracle_num` 提升聚类稳定性；真实角色名映射需要后续接入参考声纹匹配。

---

## 引擎 API

### 健康 `GET /{provider_id}/v1/health`

```bash
curl http://127.0.0.1:6006/local_index_tts/v1/health
# {"provider_id":"local_index_tts","status":"healthy"}
```

### 音色 `GET /{provider_id}/v1/voices`

```bash
curl http://127.0.0.1:6006/local_index_tts/v1/voices
```

### 合成 `POST /{provider_id}/v1/synthesize`

**JSON**（文件路径 或 base64）：

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -d '{
    "text": "你好。",
    "voice_id": "index-default",
    "language": "zh",
    "parameters": {
      "speed": 1.0,
      "pitch": 0.0,
      "volume": 1.0,
      "reference_audio": "/home/test.wav",
      "extra": {}
    },
    "output": {"format": "wav"}
  }'
```

| reference_audio 格式 | 示例 |
|---------------------|------|
| 文件路径 | `"/home/test.wav"` |
| base64 | `"data:audio/wav;base64,UklGRiQA..."` |
| null | 不传（需已通过 clone 注册 voice_id） |

**multipart**（直接上传文件）：

```bash
curl -sS -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -F 'request={"text":"你好","voice_id":"index-default"}' \
  -F "reference_audio=@speaker.wav" \
  -F "emotion_reference_audio=@emo.wav"
```

### 克隆 `POST /{provider_id}/v1/clone`

上传参考音频注册音色。之后合成只需 voice_id。

```bash
curl -sS -X POST http://127.0.0.1:6006/local_index_tts/v1/clone \
  -F "audio=@speaker.wav" \
  -F "name=我的音色" \
  -F "text=参考文本" \
  -F "language=zh" \
  -F "emotion=calm"
# {"voice_id":"wo-de-yin-se","status":"ready",...}
```

```bash
# 之后合成只需 voice_id
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -d '{"text":"你好","voice_id":"wo-de-yin-se"}'
```

---

## 管理 API

所有路由同时存在于 `/v1/*` 和 `/{provider_id}/v1/*` 下。

### 列表

```bash
curl http://127.0.0.1:6006/local_index_tts/v1/providers
curl http://127.0.0.1:6006/local_index_tts/v1/providers/local_voxcpm
curl http://127.0.0.1:6006/local_index_tts/v1/providers/status
```

### 生命周期

```bash
curl -X POST http://127.0.0.1:6006/local_index_tts/v1/providers/local_index_tts/start
curl -X POST http://127.0.0.1:6006/local_index_tts/v1/providers/local_voxcpm/stop
curl -X POST http://127.0.0.1:6006/local_index_tts/v1/providers/local_index_tts/restart
```

### 日志

```bash
curl "http://127.0.0.1:6006/local_index_tts/v1/logs?lines=100"
curl "http://127.0.0.1:6006/local_index_tts/v1/providers/local_index_tts/logs?stream=stderr&lines=50"
```

---

## 请求结构

### Synthesize

```json
{
  "text": "合成文本",
  "voice_id": "音色 ID",
  "language": "zh",
  "parameters": {
    "speed": 1.0,
    "pitch": 0.0,
    "volume": 1.0,
    "emotion": null,
    "emotion_intensity": null,
    "instruction": null,
    "reference_audio": null,
    "reference_text": null,
    "extra": {}
  },
  "output": {"format": "wav", "sample_rate": null}
}
```

### IndexTTS2 `extra` 参数

所有参数即时生效，**无需重启模型**。

#### 情感控制

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `emo_alpha` | float | 1.0 | 情感强度。音频分离模式 0→2（0=纯说话人音色），向量模式 0→1 |
| `emo_vector` | list[float] | null | 8 维情感向量 `[开心, 愤怒, 悲伤, 害怕, 厌恶, 忧郁, 惊讶, 平静]` |
| `emo_text` | str | null | 情感文本描述（如"悲伤、缓慢"），配合 `use_emo_text` |
| `use_emo_text` | bool | false | 用 Qwen Emo 模型从文本提取情感向量 |
| `use_random` | bool | false | 随机匹配情感模板（增加多样性） |

#### 音色-情感分离

传 `emotion_reference_audio`（base64 或文件路径）可实现音色和情感独立的两个音频源：

```json
{
  "extra": {
    "emotion_reference_audio": "data:audio/wav;base64,...",
    "emo_alpha": 1.5
  }
}
```

- `reference_audio` → 决定"谁在说话"（音色）
- `emotion_reference_audio` → 决定"怎么说话"（情感语气）
- `emo_alpha` > 1.0 时情感比参考更强烈，< 1.0 时更弱

#### GPT 采样

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `top_k` | int | 5 | Top-K 采样 |
| `top_p` | float | 1.0 | Top-P（nucleus）采样 |
| `temperature` | float | 1.0 | 采样温度，越高越随机 |
| `repetition_penalty` | float | 1.35 | 重复惩罚，越高越少重复 |
| `seed` | int | -1 | 随机种子（-1=随机），设固定值可复现结果 |

#### 文本切分 & 性能

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_text_tokens_per_segment` | int | 120 | 每段最大 token 数，越小分段越多 |
| `interval_silence` | int | 200 | 段落间静音间隔（毫秒） |
| `text_split_method` | str | "cut5" | 文本切分策略 |
| `split_bucket` | bool | true | 是否使用分桶优化 |
| `batch_size` | int | 1 | 批量推理大小 |
| `batch_threshold` | float | 0.75 | 批量合并阈值 |
| `fragment_interval` | float | 0.3 | 片段间间隔（秒） |
| `parallel_infer` | bool | true | 并行推理 |
| `streaming_mode` | bool | false | 流式输出模式 |
| `quick_streaming_tokens` | int | 0 | 快速流式 token 数 |

#### 其他

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `verbose` | bool | false | 输出详细推理日志到引擎 stderr |
| `more_segment_before` | int | 0 | 提前生成更多片段 |

```json
{
  "text": "你好，今天天气真好。",
  "voice_id": "index-default",
  "parameters": {
    "reference_audio": "/home/test.wav",
    "extra": {
      "emo_alpha": 1.2,
      "temperature": 0.8,
      "top_k": 10,
      "seed": 42,
      "verbose": true
    }
  }
}
```

---

## 响应

| Header | 说明 |
|--------|------|
| `Content-Type` | `audio/wav` |
| `X-Provider-Id` | provider ID |
| `X-Audio-Duration` | 音频时长（秒） |
| `X-Sample-Rate` | 采样率（Hz） |

错误：

```json
{"error": {"code": "INTERNAL_ERROR", "message": "...", "details": {}}}
```

常见错误码：`VOICE_NOT_FOUND`、`INVALID_REQUEST`、`PROVIDER_NOT_FOUND`、`ENDPOINT_NOT_AVAILABLE`。

---

## 日志

```
bobogen-gateway/logs/
├── gateway.log
└── local_index_tts/
    ├── stdout.log
    └── stderr.log
```

## MCP 协议

MCP Server 内嵌在 Gateway 中，SSE 端点：

```
GET /local_index_tts/v1/mcp/sse
POST /local_index_tts/v1/mcp/messages/
```

### 客户端配置

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "bobogen": {
      "url": "https://xxx:8443/local_index_tts/v1/mcp/sse"
    }
  }
}
```

**Claude Code / Cursor**（项目 `.claude/settings.local.json` 或 `~/.claude/mcp.json`）：

```json
{
  "mcpServers": {
    "bobogen": {
      "type": "sse",
      "url": "https://xxx:8443/local_index_tts/v1/mcp/sse"
    }
  }
}
```

### 工具列表

#### tts_synthesize — 语音合成

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | str | 必填 | 合成文本 |
| `voice_id` | str | `"index-default"` | 音色 ID |
| `provider_id` | str | `"local_index_tts"` | Provider ID |
| `language` | str | `"zh"` | 语言 |
| `speed` | float | `1.0` | 语速 |
| `reference_audio` | str | null | 参考音频 base64 |
| `emotion_reference_audio` | str | null | 情感参考音频 base64 |
| `emo_alpha` | float | `1.0` | 情感强度 |

返回 `audio_base64`（WAV）+ `duration_seconds` + `sample_rate`。

#### tts_clone_voice — 注册音色

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `audio_base64` | str | 必填 | 参考音频 base64 |
| `name` | str | 必填 | 音色名称 |
| `text` | str | `""` | 参考文本 |
| `language` | str | `"zh"` | 语言 |
| `emotion` | str | `""` | 情绪标签 |
| `provider_id` | str | `"local_index_tts"` | Provider ID |

返回 `voice_id`。

#### 查询 & 管理

| 工具 | 说明 |
|------|------|
| `tts_list_voices` | 列出音色（含 clone/design profile） |
| `tts_list_providers` | 列出所有引擎 |
| `tts_provider_status` | 查看引擎运行状态 |
| `tts_start_provider` | 启动引擎 |
| `tts_stop_provider` | 停止引擎 |
| `tts_restart_provider` | 重启引擎 |
| `tts_provider_logs` | 查看引擎日志 |

### Stdio 模式（本地）

```json
{
  "mcpServers": {
    "bobogen": {
      "command": "python3",
      "args": ["-m", "app.routers.mcp_stdio", "--gateway", "http://127.0.0.1:6006"]
    }
  }
}
```

> Stdio 模式无需额外端口，MCP Server 作为子进程通过 stdin/stdout 通信。
