# BoboGen API Reference

> 更新时间：2026-08-12
> Gateway `:6006`

客户端只需配置一个 `baseUrl`：

```
http://127.0.0.1:6006/index_tts_2
```

所有接口都在 `/{provider_id}/v1/*` 下，也可通过 `/v1/*` 直接访问（不限定 provider）。

新一代统一生成协议直接使用 Gateway 根路径：

```
http://127.0.0.1:6006/v1/generate
```

## Provider ID

| Provider ID | 引擎 | 端口 |
|-------------|------|------|
| `index_tts_2` | IndexTTS2 | 5104 |
| `voxcpm2` | VoxCPM2 | 5105 |
| `gpt_sovits_v2pro` | GPT-SoVITS | 5103 |
| `f5_tts` | F5-TTS | 5102 |
| `cosyvoice2` | CosyVoice2 | 5101 |
| `stable_audio_3_small_sfx` | Stable Audio 3 Small-SFX | 5106 |
| `qwen3_asr_0_6b` | Qwen3-ASR 0.6B | 5110 |
| `qwen3_asr_1_7b` | Qwen3-ASR 1.7B | 5111 |
| `qwen3_forced_aligner_0_6b` | Qwen3 ForcedAligner 0.6B | 5112 |
| `campplus_speaker_diarization` | CAM++ Speaker Diarization | 5113 |
| `tiger_dnr` | TIGER-DnR 对白/背景声分离 | 5114 |

### 版本化本地 TTS

对本地 TTS，`provider_type` 是稳定的引擎家族名，`provider_id` 与 `model_id` 是可并存的具体版本标识。Gateway 会拒绝重复的 provider ID、有效 model ID 或 `host:port`；对于本地 `process` provider，还会强制端口全局唯一，避免新版本因不同 YAML host 值而静默覆盖旧版本或抢占端口。

| provider_id / model_id | provider_type | 版本化运行目录 |
|------------------------|---------------|----------------|
| `cosyvoice2` | `cosyvoice` | `profiles/cosyvoice2` |
| `f5_tts` | `f5-tts` | `profiles/f5_tts` |
| `gpt_sovits_v2pro` | `gptsovits` | `profiles/gpt_sovits_v2pro`、`outputs/gpt_sovits_v2pro` |
| `index_tts_2` | `indextts` | 既有 IndexTTS2 配置 |
| `voxcpm2` | `voxcpm` | `profiles/voxcpm2`、`outputs/voxcpm2` |

`gpt_sovits_v2pro` 要求显式配置的 `s1v3.ckpt`、`v2Pro/s2Gv2Pro.pth`、BERT、CN-HuBERT 和 `sv/pretrained_eres2netv2w24s4ep4.ckpt` 路径全部存在；`voxcpm2` 要求 `config.json`、`model.safetensors`、`audiovae.pth` 与 `tokenizer.json` 全部存在，且 `config.json.architecture` 必须为 `voxcpm2`。二者不会扫描旧权重目录或静默回退；缺失或版本不匹配时启动/预加载会失败并返回具体路径或架构错误。

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
      "id": "f5_tts",
      "name": "F5-TTS",
      "provider_id": "f5_tts",
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
    "model": "f5_tts",
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
  -F 'request={"model":"f5_tts","task":"tts.speech","input":{"text":"你好","voice":"f5-default"},"parameters":{"reference_audio":{"kind":"upload","field":"ref_audio"}}}' \
  -F "ref_audio=@speaker.wav"
```

当调用方（例如 BoboVoxClient）部署在另一台机器时，应使用 `upload` 或 `data_uri`，
不要把调用方本机路径放进 `path`。`upload` 会由 Gateway 保存为服务端临时文件，
本次请求直接使用该参考音频；因此 `input.voice` 可以是客户端自己的逻辑音色 ID，
不要求服务端 profile 目录中预先存在同名 profile。

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

### TIGER-DnR 异步对白/背景声分离

模型 ID 为 `tiger-dnr`，任务为 `audio.separate`。公开产物固定为：

- `dialogue`：模型估计的对白。
- `background`：对齐采样率、声道和 frame count 后，以
  `decoded_original - dialogue` 得到的全部非对白声音。

输出固定为 32-bit float WAV。长音频走单 GPU worker、分块推理和异步任务接口，
不会把完整上传或产物一次性载入 Gateway 内存。

创建服务器本地文件任务：

```bash
curl -sS -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:6006/v1/jobs \
  -d '{
    "model": "tiger-dnr",
    "task": "audio.separate",
    "input": {
      "audio": {"kind": "path", "path": "D:/media/source.m4a"}
    },
    "parameters": {},
    "output": {"format": "wav"}
  }'
```

也支持 multipart 流式上传：

```bash
curl -sS -X POST http://127.0.0.1:6006/v1/jobs \
  -F 'request={"model":"tiger-dnr","task":"audio.separate","input":{"audio":{"kind":"upload","field":"audio"}},"parameters":{},"output":{"format":"wav"}}' \
  -F "audio=@source.m4a"
```

创建成功返回 HTTP 202 和 opaque job ID。随后使用：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/jobs/{id}` | 查询状态、阶段、0..1 进度和产物元数据 |
| POST | `/v1/jobs/{id}/cancel` | 请求安全取消 |
| GET | `/v1/jobs/{id}/artifacts/{artifactId}` | 流式下载 WAV |
| DELETE | `/v1/jobs/{id}` | 清理任务、私有输入、manifest 和产物 |

状态为 `queued`、`running`、`cancelling`、`succeeded`、`failed` 或
`cancelled`。客户端可在 cancel 后立即 DELETE：DELETE 返回 204，运行中的
worker 会在当前安全点停止并完成延迟清理，之后再次查询返回 404。

成功响应示例：

```json
{
  "id": "opaque-id",
  "model": "tiger-dnr",
  "task": "audio.separate",
  "status": "succeeded",
  "progress": {"phase": "validating", "fraction": 1.0, "message": "分离产物校验完成"},
  "artifacts": [
    {"id": "opaque-artifact-id", "role": "dialogue", "filename": "dialogue.wav", "content_type": "audio/wav"},
    {"id": "opaque-artifact-id", "role": "background", "filename": "background.wav", "content_type": "audio/wav"}
  ]
}
```

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

需要先在 Hugging Face 接受 `stabilityai/stable-audio-3-small-sfx` 模型条款。服务启动脚本默认读取 `services/stable-audio3-service/.venv`；如需使用其他 Python，设置 `STABLE_AUDIO3_PYTHON`，但该路径仍必须位于 BoboGenServer 内。

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

Qwen3 ForcedAligner 通过统一生成协议接入，模型 ID 为 `qwen3_forced_aligner_0_6b`，任务为 `audio.align`。服务使用官方 `Qwen/Qwen3-ForcedAligner-0.6B-hf` 和 `AutoModelForTokenClassification`，不再经过旧版完整语言模型词表 logits。它不做语音识别，只负责把可信文本对齐到音频，返回片段内时间和工程全局时间。客户端仍负责 FFmpeg 静音检测、VAD 粗切、字幕 cue 拆分和编辑策略。

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
curl http://127.0.0.1:6006/index_tts_2/v1/health
# {"provider_id":"index_tts_2","status":"healthy"}
```

### 音色 `GET /{provider_id}/v1/voices`

```bash
curl http://127.0.0.1:6006/index_tts_2/v1/voices
```

### 合成 `POST /{provider_id}/v1/synthesize`

**JSON**（文件路径 或 base64）：

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/index_tts_2/v1/synthesize \
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
  -X POST http://127.0.0.1:6006/index_tts_2/v1/synthesize \
  -F 'request={"text":"你好","voice_id":"index-default"}' \
  -F "reference_audio=@speaker.wav" \
  -F "emotion_reference_audio=@emo.wav"
```

### 克隆 `POST /{provider_id}/v1/clone`

上传参考音频注册音色。之后合成只需 voice_id。

```bash
curl -sS -X POST http://127.0.0.1:6006/index_tts_2/v1/clone \
  -F "audio=@speaker.wav" \
  -F "voice_id=voice_shared_001" \
  -F "name=我的音色" \
  -F "text=参考文本" \
  -F "language=zh" \
  -F "emotion=calm"
# {"voice_id":"voice_shared_001","status":"ready",...}
```

`voice_id` 是可选字段。旧调用可以用该接口登记服务器本地 profile；但新的客户端解耦链路不依赖它：
客户端创建音色时只保存自己的参考素材，合成时通过 `/v1/generate` 上传素材即可。
未提供 `voice_id` 时，为兼容旧调用，服务仍按 `name` 生成 slug。

该接口只登记参考音频和 profile 元数据，不执行推理、不生成试听音频，也不要求在登记阶段加载模型权重。
Gateway 的旧 clone 路由也不会为了登记动作自动启动模型进程；模型权重和依赖会在后续合成请求中按具体模型校验并按需加载。

```bash
# 之后合成只需 voice_id
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/index_tts_2/v1/synthesize \
  -d '{"text":"你好","voice_id":"wo-de-yin-se"}'
```

---

## 管理 API

所有路由同时存在于 `/v1/*` 和 `/{provider_id}/v1/*` 下。

### 列表

```bash
curl http://127.0.0.1:6006/index_tts_2/v1/providers
curl http://127.0.0.1:6006/index_tts_2/v1/providers/voxcpm2
curl http://127.0.0.1:6006/index_tts_2/v1/providers/status
```

### 生命周期

```bash
curl -X POST http://127.0.0.1:6006/index_tts_2/v1/providers/index_tts_2/start
curl -X POST http://127.0.0.1:6006/index_tts_2/v1/providers/voxcpm2/stop
curl -X POST http://127.0.0.1:6006/index_tts_2/v1/providers/index_tts_2/restart
```

### 日志

```bash
curl "http://127.0.0.1:6006/index_tts_2/v1/logs?lines=100"
curl "http://127.0.0.1:6006/index_tts_2/v1/providers/index_tts_2/logs?stream=stderr&lines=50"
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
└── index_tts_2/
    ├── stdout.log
    └── stderr.log
```

## MCP 协议

MCP Server 内嵌在 Gateway 中，SSE 端点：

```
GET /index_tts_2/v1/mcp/sse
POST /index_tts_2/v1/mcp/messages/
```

### 客户端配置

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "bobogen": {
      "url": "https://xxx:8443/index_tts_2/v1/mcp/sse"
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
      "url": "https://xxx:8443/index_tts_2/v1/mcp/sse"
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
| `provider_id` | str | `"index_tts_2"` | Provider ID |
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
| `provider_id` | str | `"index_tts_2"` | Provider ID |

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
