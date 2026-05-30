# Local TTS Service Endpoints

> 日期：2026-04-10  
> 适用服务：`cosyvoice-service` / `f5tts-service` / `gptsovits-service` / `voxcpm-service`

## Service Base URLs

| Service | Base URL | Default Port |
|---|---|---|
| CosyVoice | `http://127.0.0.1:5101` | `5101` |
| F5-TTS | `http://127.0.0.1:5102` | `5102` |
| GPT-SoVITS | `http://127.0.0.1:5103` | `5103` |
| VoxCPM2 | `http://127.0.0.1:5105` | `5105` |

## Supported Protocol Endpoints

All services expose the same protocol-shaped HTTP surface:

| Method | Path | Status |
|---|---|---|
| `GET` | `/v1/health` | Implemented |
| `GET` | `/v1/voices` | Implemented |
| `POST` | `/v1/synthesize` | Implemented |
| `POST` | `/v1/clone` | Implemented |
| `GET` | `/v1/clone/{task_id}/status` | Implemented |
| `POST` | `/v1/synthesize/stream` | Reserved, currently returns `404 ENDPOINT_NOT_AVAILABLE` |
| `POST` | `/v1/design` | Implemented by `voxcpm-service`, reserved on the others |

## Authentication

If environment variable `LOCAL_TTS_API_KEY` is configured, every request must include:

```http
Authorization: Bearer <apiKey>
```

If `LOCAL_TTS_API_KEY` is not configured, the services accept unauthenticated local requests.

## Health Check

Example:

```powershell
curl.exe http://127.0.0.1:5101/v1/health
curl.exe http://127.0.0.1:5102/v1/health
curl.exe http://127.0.0.1:5103/v1/health
curl.exe http://127.0.0.1:5105/v1/health
```

Typical response:

```json
{
  "status": "ok",
  "model": "GPT-SoVITS",
  "version": "local"
}
```

`GPT-SoVITS` and `VoxCPM2` currently also return `ready: true/false`.

## Voices

Example:

```powershell
curl.exe http://127.0.0.1:5101/v1/voices
curl.exe http://127.0.0.1:5102/v1/voices
curl.exe http://127.0.0.1:5103/v1/voices
curl.exe http://127.0.0.1:5105/v1/voices
```

The response shape is:

```json
{
  "voices": [
    {
      "voice_id": "default",
      "name": "Default",
      "language": ["zh"],
      "gender": "female",
      "description": "voice description",
      "tags": ["clone"],
      "metadata": {}
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 100
}
```

## Synthesize

Request:

```json
{
  "text": "你好，这是一次协议调用测试。",
  "voice_id": "default",
  "language": "zh",
  "parameters": {
    "speed": 1.0,
    "emotion": "calm",
    "emotion_intensity": 0.8,
    "instruction": "用温柔语气说",
    "reference_audio": null,
    "reference_text": null,
    "extra": {}
  },
  "output": {
    "format": "wav",
    "sample_rate": 24000
  }
}
```

Example:

```powershell
$payload = @{
  text = "你好，这是一次协议调用测试。"
  voice_id = "default"
  language = "zh"
  parameters = @{
    speed = 1.0
    extra = @{}
  }
  output = @{
    format = "wav"
  }
} | ConvertTo-Json -Depth 6

$payload | Set-Content -Path "$env:TEMP\local-tts-request.json" -Encoding UTF8

curl.exe -sS ^
  -H "Content-Type: application/json" ^
  -o synth.wav ^
  -X POST http://127.0.0.1:5103/v1/synthesize ^
  --data-binary "@$env:TEMP\local-tts-request.json"
```

Success response headers typically include:

- `Content-Type: audio/wav`
- `X-Sample-Rate: ...`
- `X-Audio-Duration: ...` when available

## Clone

`/v1/clone` creates a reusable voice profile from one reference audio file.

Example:

```powershell
curl.exe -sS ^
  -X POST http://127.0.0.1:5103/v1/clone ^
  -F "audio=@E:/AiModel/tts/GPT-SoVITS-v2-240821/pangbai.wav" ^
  -F "name=pangbai" ^
  -F "text=庞白参考文本" ^
  -F "language=zh" ^
  -F "emotion=calm"
```

Typical response:

```json
{
  "voice_id": "pangbai",
  "status": "ready",
  "name": "pangbai",
  "metadata": {
    "language": "zh",
    "reference_audio": "E:\\AiModel\\tts\\services\\gptsovits-service\\data\\profiles\\pangbai\\reference.wav",
    "reference_text": "庞白参考文本",
    "emotion": "calm"
  }
}
```

## Clone Status

All current clone-capable services implement synchronous clone, so status queries typically return `ready` immediately.

Example:

```powershell
curl.exe http://127.0.0.1:5103/v1/clone/pangbai/status
```

Typical response:

```json
{
  "task_id": "pangbai",
  "status": "ready",
  "voice_id": "pangbai",
  "name": "pangbai",
  "metadata": {}
}
```

## Design

`/v1/design` creates a reusable instruction-based voice profile. This endpoint is currently implemented by `voxcpm-service`.

Example:

```powershell
$payload = @{
  name = "warm-host"
  parameters = @{
    instruction = "温柔、年轻、自然，适合播客旁白"
    language = "zh"
    emotion = "warm"
  }
} | ConvertTo-Json -Depth 6

curl.exe -sS ^
  -H "Content-Type: application/json" ^
  -X POST http://127.0.0.1:5105/v1/design ^
  --data-binary $payload
```

Typical response:

```json
{
  "voice_id": "warm-host",
  "name": "warm-host",
  "status": "ready",
  "metadata": {
    "instruction": "温柔、年轻、自然，适合播客旁白",
    "language": "zh",
    "emotion": "warm"
  }
}
```

## Service-Specific Notes

### CosyVoice

- Base URL: `http://127.0.0.1:5101`
- Preset SFT voice example: `voice_id = "中文女"`
- Zero-shot clone profiles are stored under:
  `services/cosyvoice-service/data/profiles`

### F5-TTS

- Base URL: `http://127.0.0.1:5102`
- Default reference-driven voice example: `voice_id = "f5-default"`
- Clone profiles are stored under:
  `services/f5tts-service/data/profiles`

### GPT-SoVITS

- Base URL: `http://127.0.0.1:5103`
- Default reference-driven voice example: `voice_id = "default"`
- Clone profiles are stored under:
  `services/gptsovits-service/data/profiles`

### VoxCPM2

- Base URL: `http://127.0.0.1:5105`
- Default instruction-first voice example: `voice_id = "voxcpm2-default"`
- Clone profiles are stored under:
  `services/voxcpm-service/data/profiles/clones`
- Design profiles are stored under:
  `services/voxcpm-service/data/profiles/designs`
- `parameters.instruction` is the primary entry for voice design and controllable cloning

## One-Click Scripts

### CosyVoice

- [start.ps1](E:\AiModel\tts\services\cosyvoice-service\start.ps1)
- [healthcheck.ps1](E:\AiModel\tts\services\cosyvoice-service\healthcheck.ps1)
- [clone-test.ps1](E:\AiModel\tts\services\cosyvoice-service\clone-test.ps1)

### F5-TTS

- [start.ps1](E:\AiModel\tts\services\f5tts-service\start.ps1)
- [healthcheck.ps1](E:\AiModel\tts\services\f5tts-service\healthcheck.ps1)
- [clone-test.ps1](E:\AiModel\tts\services\f5tts-service\clone-test.ps1)

### GPT-SoVITS

- [start.ps1](E:\AiModel\tts\services\gptsovits-service\start.ps1)
- [healthcheck.ps1](E:\AiModel\tts\services\gptsovits-service\healthcheck.ps1)
- [clone-test.ps1](E:\AiModel\tts\services\gptsovits-service\clone-test.ps1)

### VoxCPM2

- [start.ps1](E:\AiModel\tts-server\services\voxcpm-service\start.ps1)
- [healthcheck.ps1](E:\AiModel\tts-server\services\voxcpm-service\healthcheck.ps1)
