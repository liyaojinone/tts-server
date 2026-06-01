# Local TTS API Reference

> 更新时间：2026-06-01
> Gateway `:6006`

## Provider ID

| Provider ID | 引擎 | 端口 |
|-------------|------|------|
| `local_index_tts` | IndexTTS2 | 5104 |
| `local_voxcpm` | VoxCPM2 | 5105 |
| `local_gpt_sovits` | GPT-SoVITS | 5103 |
| `local_f5_tts` | F5-TTS | 5102 |
| `local_cosyvoice2` | CosyVoice2 | 5101 |

客户端配置 `baseUrl`：

```
http://127.0.0.1:6006/{provider_id}
```

例如 `http://127.0.0.1:6006/local_index_tts`，所有引擎 API 都在 `/{provider_id}/v1/*` 下。

## Authentication

若设置环境变量 `LOCAL_TTS_API_KEY`，所有请求需带：

```http
Authorization: Bearer <apiKey>
```

未设置则无需认证。

---

## 引擎 API（`/{provider_id}/v1/*`）

### 健康 `GET /{provider_id}/v1/health`

```bash
curl http://127.0.0.1:6006/local_index_tts/v1/health
# {"provider_id":"local_index_tts","status":"healthy"}
```

### 音色 `GET /{provider_id}/v1/voices`

```bash
curl http://127.0.0.1:6006/local_index_tts/v1/voices
```

```json
{
  "voices": [{
    "voice_id": "index-default",
    "name": "IndexTTS Default",
    "language": ["zh", "en"],
    "tags": ["reference", "default"],
    "metadata": {}
  }],
  "total": 1
}
```

### 合成 `POST /{provider_id}/v1/synthesize`

三种传参方式。

#### JSON（文件路径 或 base64）

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -d '{
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

reference_audio 支持：

| 格式 | 示例 |
|------|------|
| 文件路径 | `"/home/test.wav"` |
| base64 | `"data:audio/wav;base64,UklGRiQA..."` |
| null | 不传（通过 clone 注册的 voice_id 代替） |

#### multipart（直接上传文件）

```bash
curl -sS -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -F 'request={"text":"你好","voice_id":"index-default"}' \
  -F "reference_audio=@speaker.wav" \
  -F "emotion_reference_audio=@emo.wav"
```

### 克隆 `POST /{provider_id}/v1/clone`

上传参考音频注册音色，得到 voice_id 后合成无需再传 reference_audio。

```bash
curl -sS -X POST http://127.0.0.1:6006/local_index_tts/v1/clone \
  -F "audio=@speaker.wav" \
  -F "name=我的音色" \
  -F "text=参考文本内容" \
  -F "language=zh" \
  -F "emotion=calm"
```

```json
{"voice_id":"wo-de-yin-se","status":"ready","name":"我的音色",...}
```

之后合成只需 voice_id：

```bash
curl -sS -H "Content-Type: application/json" -o out.wav \
  -X POST http://127.0.0.1:6006/local_index_tts/v1/synthesize \
  -d '{"text":"你好","voice_id":"wo-de-yin-se"}'
```

---

## 管理 API（`/v1/*`）

### `GET /v1/health` — Gateway 自身健康

```bash
curl http://127.0.0.1:6006/v1/health
# {"status":"ok"}
```

### `GET /v1/providers` — 列出所有 provider

```bash
curl http://127.0.0.1:6006/v1/providers
```

### `GET /v1/providers/{id}` — 查看 provider

```bash
curl http://127.0.0.1:6006/v1/providers/local_index_tts
```

---

## 运维 API（`/internal/*`）

### 引擎生命周期

```bash
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/start
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/stop
curl -X POST http://127.0.0.1:6006/internal/providers/local_index_tts/restart
```

### 状态查询

```bash
curl http://127.0.0.1:6006/internal/providers/status
```

### 日志

```bash
# Gateway 日志
curl "http://127.0.0.1:6006/internal/logs?lines=100"

# 引擎日志
curl "http://127.0.0.1:6006/internal/providers/local_index_tts/logs?stream=stderr&lines=50"
```

---

## IndexTTS2 emotion control（`extra` 参数）

```json
{
  "extra": {
    "emotion_reference_audio": "data:audio/wav;base64,...",
    "emo_text": "悲伤",
    "emo_alpha": 1.0,
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

## 直连引擎服务（绕过 Gateway）

直连引擎时端口不同，路径一致：`/{provider_id}/v1/*` 变为 `http://127.0.0.1:5104/v1/*`，实际就是 service-kit 标准的 `/v1/synthesize`、`/v1/clone` 等路径。
