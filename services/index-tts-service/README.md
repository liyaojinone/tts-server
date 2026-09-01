# index-tts-service

Protocol-compliant `IndexTTS2` service built on top of the shared local TTS packages.

## Prerequisites

- `models/index-tts/repo` must exist
- `models/index-tts/checkpoints` must contain the downloaded model files
- `services/index-tts-service/.venv` must be available

## Run

Use the bundled script:

```powershell
.\start.ps1
```

The service starts without loading `IndexTTS2` by default. Profile registration only writes the reference asset; the model is loaded lazily on the first synthesis request. Set `INDEXTTS_PRELOAD_ON_STARTUP=true` when a warm startup is explicitly required.

Or run directly:

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5104
```

Base URL:

```text
http://127.0.0.1:5104
```

Health check:

```powershell
.\healthcheck.ps1
```

## Current behavior

- serves `/v1/health`
- serves `/v1/voices`
- serves `/v1/synthesize`
- serves `/v1/clone`
- serves `/v1/clone/{task_id}/status`
- supports cloned reusable voice profiles
- supports independent emotion reference audio through `parameters.extra.emotion_reference_audio`
- loads the model lazily on synthesis and reuses the same loaded instance across requests
- writes generated audio into `models/index-tts/outputs`

## Gateway provider

The gateway provider id is:

```text
indextts-default
```
