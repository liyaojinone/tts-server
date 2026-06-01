# Local TTS API Reference

> 更新时间：2026-06-01
> 入口：Gateway `:6006`（推荐），也可直连各引擎服务 `:5101` ~ `:5105`

## Provider ID

| Provider ID | 引擎 | 端口 |
|-------------|------|------|
| `local_index_tts` | IndexTTS2 | 5104 |
| `local_voxcpm` | VoxCPM2 | 5105 |
| `local_gpt_sovits` | GPT-SoVITS | 5103 |
| `local_f5_tts` | F5-TTS | 5102 |
| `local_cosyvoice2` | CosyVoice2 | 5101 |

## Authentication

若设置环境变量 `LOCAL_TTS_API_KEY`，所有请求需带：

```http
Authorization: Bearer <apiKey>
```

未设置则无需认证。

---

## Gateway Endpoints（:6006）

### 健康 & 状态

**`GET /v1/health`**

```bash
curl http://127.0.0.1:6006/v1/health
# {"status":"ok"}
```

**`GET /v1/providers`**

```bash
curl http://127.0.0.1:6006/v1/providers
# {"providers":[{"provider_id":"local_index_tts","provider_type":"indextts","display_name":"IndexTTS Default","enabled":true}]}
```

**`GET /v1/providers/{id}`**

```bash
curl http://127.0.0.1:6006/v1/providers/local_index_tts
```

**`GET /v1/providers/{id}/health`**

```bash
curl http://127.0.0.1:6006/v1/providers/local_index_tts/health
# {"provider_id":"local_index_tts","status":"healthy"}
```

### 音色

**`GET /v1/providers/{id}/voices`** 或 **`GET /v1/voices?provider_id=xxx`**

```bash
curl http://127.0.0.1:6006/v1/providers/local_index_tts/voices
curl "http://127.0.0.1:6006/v1/voices?provider_id=local_index_tts"
```

Response:

```json
{
  "voices": [{
    "voice_id": "index-default",
    "name": "IndexTTS Default",
    "language": ["zh", "en"],
    "gender": null,
    "description": "IndexTTS2 reference-driven synthesis mode",
    "tags": ["reference", "default"],
    "metadata": {}
  }],
  "total": 1,
  "page": 1,
  "page_size": 100
}
```

### 合成 `POST /v1/synthesize`

三种传参方式，`reference_audio` 和 `emotion_reference_audio` 均支持。

#### 方式一：JSON（文件路径 或 base64）

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/v1/synthesize \
  -d '{
    "provider_id": "local_index_tts",
    "text": "你好，测试。",
    "voice_id": "index-default",
    "language": "zh",
    "parameters": {
      "speed": 1.0,
      "pitch": 0.0,
      "volume": 1.0,
      "emotion": null,
      "emotion_intensity": null,
      "instruction": null,
      "reference_audio": "/home/test.wav",
      "reference_text": null,
      "extra": {
        "emotion_reference_audio": null,
        "emo_text": null,
        "emo_alpha": 1.0,
        "cfg_value": 2.0,
        "inference_timesteps": 10
      }
    },
    "output": {"format": "wav", "sample_rate": null}
  }'
```

reference_audio 支持三种值：

| 格式 | 示例 |
|------|------|
| 文件路径 | `"/home/test.wav"` |
| base64 | `"data:audio/wav;base64,UklGRiQAAABXQVZF..."` |
| null | 不传（需通过 clone 注册的 voice_id 代替） |

#### 方式二：multipart（直接上传文件）

```bash
curl -sS -o out.wav \
  -X POST http://127.0.0.1:6006/v1/synthesize \
  -F 'request={"provider_id":"local_index_tts","text":"你好","voice_id":"index-default"}' \
  -F "reference_audio=@speaker.wav" \
  -F "emotion_reference_audio=@emo.wav"
```

#### 方式三：指定 provider 路径

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/v1/providers/local_index_tts/synthesize \
  -d '{"text":"你好","voice_id":"index-default","parameters":{"reference_audio":"/home/test.wav"}}'
```

### 克隆 `POST /v1/providers/{id}/clone`

上传参考音频注册音色，得到 voice_id 后合成时无需再传 reference_audio。

```bash
curl -sS -X POST http://127.0.0.1:6006/v1/providers/local_index_tts/clone \
  -F "audio=@speaker.wav" \
  -F "name=我的音色" \
  -F "text=参考文本内容" \
  -F "language=zh" \
  -F "emotion=calm"
```

Response:

```json
{
  "voice_id": "wo-de-yin-se",
  "status": "ready",
  "name": "我的音色",
  "metadata": {
    "language": "zh",
    "reference_audio": "/home/tts-server/services/index-tts-service/data/profiles/wo-de-yin-se/reference.wav",
    "reference_text": "参考文本内容",
    "emotion": "calm"
  }
}
```

之后合成只需 voice_id：

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/v1/synthesize \
  -d '{"provider_id":"local_index_tts","text":"你好","voice_id":"wo-de-yin-se"}'
```

### 引擎生命周期 `POST /internal/providers/{id}/start|stop|restart`

```bash
# 启动
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/start
# {"provider_id":"local_index_tts","status":"healthy"}

# 停止
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/stop
# {"provider_id":"local_index_tts","status":"stopped"}

# 重启
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/restart
```

### 状态查询 `GET /internal/providers/status`

```bash
curl http://127.0.0.1:6006/internal/providers/status
```

```json
{
  "providers": [{
    "provider_id": "local_index_tts",
    "status": "healthy",
    "pid": 12345,
    "port": 5104,
    "started_at": "2026-06-01T08:30:00",
    "last_health_at": "2026-06-01T08:30:05",
    "last_used_at": "2026-06-01T08:35:00",
    "startup_attempts": 1,
    "last_error": null
  }]
}
```

### 日志查询

```bash
# Gateway 日志
curl "http://127.0.0.1:6006/internal/logs?lines=100"

# 引擎日志
curl "http://127.0.0.1:6006/internal/providers/local_index_tts/logs?stream=stderr&lines=50"
```

---

## 引擎服务端点（直连 :5101 ~ :5105）

绕过 Gateway 直接调引擎时，接口一致，额外支持：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/clone/{task_id}/status` | 查询 clone 状态（当前均为同步，立即返回 ready） |
| POST | `/v1/synthesize/stream` | 流式合成（暂未实现，返回 404） |
| POST | `/v1/design` | 文本指令注册音色，仅 VoxCPM 支持 |

### IndexTTS2 emotion control（`extra` 参数）

```json
{
  "extra": {
    "emotion_reference_audio": "data:audio/wav;base64,...",
    "emo_text": "悲伤",
    "emo_alpha": 1.0,
    "emo_vector": null,
    "use_emo_text": false,
    "use_random": false,
    "interval_silence": 200,
    "max_text_tokens_per_segment": 120,
    "cfg_value": 2.0,
    "inference_timesteps": 10
  }
}
```

---

## 响应头

| Header | 说明 |
|--------|------|
| `Content-Type` | `audio/wav` |
| `X-Provider-Id` | 处理请求的 provider ID |
| `X-Audio-Duration` | 音频时长（秒） |
| `X-Sample-Rate` | 采样率（Hz） |

## 错误响应

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error",
    "details": {}
  }
}
```

常见错误码：`VOICE_NOT_FOUND`、`INVALID_REQUEST`、`PROVIDER_NOT_FOUND`、`PROVIDER_DISABLED`、`ENDPOINT_NOT_AVAILABLE`。

## 日志

```
local-tts-gateway/logs/
├── gateway.log
└── local_index_tts/
    ├── stdout.log
    └── stderr.log
```
