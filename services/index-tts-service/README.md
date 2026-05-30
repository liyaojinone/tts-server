# index-tts-service

Protocol-compliant `IndexTTS2` service built on top of the shared local TTS packages.

## Prerequisites

- `models/index-tts/repo` must exist
- `models/index-tts/checkpoints` must contain the downloaded model files
- `models/index-tts/repo/.venv` must be available

## Run

Use the bundled script:

```powershell
.\start.ps1
```

The service now preloads `IndexTTS2` during startup and keeps the model resident in memory for later requests.

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
- preloads the model on startup and reuses the same loaded instance across requests
- writes generated audio into `models/index-tts/outputs`

## Gateway provider

The gateway provider id is:

```text
indextts-default
```
