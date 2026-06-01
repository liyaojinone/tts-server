# Local TTS API Reference

> 更新时间：2026-06-01
> Gateway `:6006`

客户端只需配置一个 `baseUrl`：

```
http://127.0.0.1:6006/local_index_tts
```

所有接口都在 `/{provider_id}/v1/*` 下，也可通过 `/v1/*` 直接访问（不限定 provider）。

## Provider ID

| Provider ID | 引擎 | 端口 |
|-------------|------|------|
| `local_index_tts` | IndexTTS2 | 5104 |
| `local_voxcpm` | VoxCPM2 | 5105 |
| `local_gpt_sovits` | GPT-SoVITS | 5103 |
| `local_f5_tts` | F5-TTS | 5102 |
| `local_cosyvoice2` | CosyVoice2 | 5101 |

## Authentication

设置 `LOCAL_TTS_API_KEY` 后需带 `Authorization: Bearer <key>`。

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

### IndexTTS2 emotion（`extra` 参数）

```json
{
  "extra": {
    "emotion_reference_audio": "data:audio/wav;base64,...",
    "emo_text": "悲伤",
    "emo_alpha": 1.0,
    "use_emo_text": false,
    "cfg_value": 2.0,
    "inference_timesteps": 10
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
local-tts-gateway/logs/
├── gateway.log
└── local_index_tts/
    ├── stdout.log
    └── stderr.log
```
