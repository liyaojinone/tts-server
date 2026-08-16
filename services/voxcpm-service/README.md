# voxcpm-service

Protocol-compliant `VoxCPM2` service (`model_id: voxcpm2`) built on top of the shared local TTS packages.

## Prerequisites

- `models/voxcpm/repo` must exist
- `models/voxcpm/checkpoints` must contain the existing VoxCPM2 model files: `config.json`, `model.safetensors`, `audiovae.pth`, and `tokenizer.json`
- the runtime Python environment must be able to import `models/voxcpm/repo/src`

The provider YAML passes `VOXCPM_MODEL_ID`, `VOXCPM_EXPECTED_ARCHITECTURE=voxcpm2`, all four model-file paths, profile/output paths, host, and port explicitly. Missing files or a `config.json` whose `architecture` is not `voxcpm2` cause startup/preload to fail; the service never downloads or falls back to a different model directory or a prior VoxCPM architecture. The existing checkpoint directory is used in place and is not copied or replaced.

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
- reports `version: voxcpm2` from `/v1/health`
- supports reusable clone profiles
- supports reusable instruction-based design profiles
- preloads the model on startup when `VOXCPM_PRELOAD_ON_STARTUP=true`
- stores profile and output data under versioned `voxcpm2` paths by default
