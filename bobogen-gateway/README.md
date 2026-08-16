# BoboGen Gateway

Unified FastAPI gateway for local TTS providers.

## Purpose

This gateway exposes one HTTP interface for local TTS engines:

- `CosyVoice`
- `F5-TTS`
- `GPT-SoVITS`
- `VoxCPM2`
- `Stable Audio 3 Small-SFX`

It loads provider definitions from `configs/providers`, starts model services lazily, and forwards unified synthesize requests to provider-native APIs.

## Current endpoints

- `GET /v1/health`
- `GET /v1/models`
- `GET /v1/models/{model_id}`
- `POST /v1/generate`
- `GET /v1/providers`
- `GET /v1/providers/{provider_id}`
- `GET /v1/providers/{provider_id}/health`
- `GET /v1/providers/{provider_id}/voices`
- `POST /v1/providers/{provider_id}/synthesize`
- `GET /v1/voices?provider_id=...`
- `POST /v1/synthesize`
- `GET /v1/providers/status`
- `POST /v1/providers/{provider_id}/start`
- `POST /v1/providers/{provider_id}/stop`
- `POST /v1/providers/{provider_id}/restart`

## Provider config

Provider YAML files live in:

```text
configs/providers/
```

Included defaults:

- `cosyvoice-windows.yaml`
- `f5tts-windows.yaml`
- `gptsovits-windows.yaml`
- `indextts-windows.yaml`
- `voxcpm-windows.yaml`

Each provider defines:

- process working directory
- launch command
- port and base URL
- healthcheck path
- supported capabilities
- default logical voices

For versioned local TTS, keep `provider_type` as the stable engine family while using versioned `provider_id` and `model_id` values: `cosyvoice2`, `f5_tts`, `gpt_sovits_v2pro`, `index_tts_2`, and `voxcpm2`. Configuration loading rejects duplicate provider IDs, effective model IDs, and `host:port` endpoints, so separate versions cannot silently replace one another.

## Current provider-native mappings

- `CosyVoice` -> `POST /v1/audio/speech`
- `F5-TTS` -> `POST /tts`
- `GPT-SoVITS` -> `POST /tts`

The gateway currently expects the underlying model service to already expose a usable HTTP API. It does not modify model internals.

## Real integration notes

Validated on this machine:

- the gateway can lazily start `F5-TTS`
- the gateway can proxy `POST /v1/synthesize` to `F5-TTS`
- the gateway returns audio bytes back to the caller

Important implementation details:

- localhost health checks and synthesize forwarding use `httpx(..., trust_env=False)` to avoid proxy interference
- `F5-TTS` was patched to:
  - expose `/health`
  - read `TTS_HOST` and `TTS_PORT`
  - prefer local cached vocoder files
  - prefer local checkpoint files before downloading

`CosyVoice`, `GPT-SoVITS`, and `VoxCPM2` expose `/v1/health`. The GPT-SoVITS and VoxCPM2 services report `gpt_sovits_v2pro` and `voxcpm2` respectively and require their configured local model paths instead of scanning or falling back to another version.

## Install

Use a Python environment with:

- `fastapi`
- `httpx`
- `pydantic`
- `pyyaml`
- `uvicorn`
- `pytest`

## Run

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090
```

Run the command inside `bobogen-gateway/`.

## Example request

New generation API:

```json
POST /v1/generate
{
  "model": "f5_tts",
  "task": "tts.speech",
  "input": {
    "text": "你好",
    "voice": "f5-default",
    "language": "zh"
  },
  "parameters": {
    "reference_audio": {"kind": "path", "path": "E:/AiModel/tts/ref.wav"},
    "reference_text": "你好"
  },
  "output": {
    "format": "wav",
    "sample_rate": 24000
  }
}
```

Legacy synthesize API remains available:

```json
POST /v1/synthesize
{
  "provider_id": "f5_tts",
  "text": "你好",
  "voice_id": "f5-default",
  "language": "zh",
  "parameters": {
    "reference_audio": "E:/AiModel/tts/ref.wav",
    "reference_text": "你好"
  },
  "output": {
    "format": "wav",
    "sample_rate": 24000
  }
}
```

Stable Audio 3 Small-SFX:

```json
POST /v1/generate
{
  "model": "stable_audio_3_small_sfx",
  "task": "audio.generate",
  "input": {
    "prompt": "short cinematic whoosh impact"
  },
  "parameters": {
    "duration": 7,
    "seed": 1234
  },
  "output": {
    "format": "wav",
    "sample_rate": 44100
  }
}
```

## Tests

```bash
python -m pytest tests -v
```
