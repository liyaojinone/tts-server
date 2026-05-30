# voxcpm-service

Protocol-compliant `VoxCPM2` service built on top of the shared local TTS packages.

## Prerequisites

- `models/voxcpm/repo` must exist
- `models/voxcpm/checkpoints` must contain the downloaded VoxCPM2 model files
- the runtime Python environment must be able to import `models/voxcpm/repo/src`

## Run

Use the bundled script:

```powershell
.\start.ps1
```

Or run directly:

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5105
```

Base URL:

```text
http://127.0.0.1:5105
```

## Current behavior

- serves `/v1/health`
- serves `/v1/voices`
- serves `/v1/synthesize`
- serves `/v1/clone`
- serves `/v1/clone/{task_id}/status`
- serves `/v1/design`
- supports reusable clone profiles
- supports reusable instruction-based design profiles
- preloads the model on startup when `VOXCPM_PRELOAD_ON_STARTUP=true`
