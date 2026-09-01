# f5tts-service

Protocol-compliant `F5-TTS` service built on top of the shared local TTS packages.

## Install

Use the `F5-TTS` environment, then install the shared packages:

```bash
pip install -e ..\..\bobogen-protocol
pip install -e ..\..\bobogen-service-kit
```

## Run

Run with the `F5-TTS` Python environment:

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5102
```

Base URL:

```text
http://127.0.0.1:5102
```

Or use the bundled scripts:

```powershell
.\start.ps1
.\healthcheck.ps1
.\clone-test.ps1
```

By default `start.ps1` reads upstream source from `models\f5-tts\repo` and Python from `services\f5tts-service\.venv\Scripts\python.exe`. It starts the official `F5TTS_v1_Base` model and requires its local files at:

```text
models\f5-tts\repo\ckpts\F5TTS_v1_Base\model_1250000.safetensors
models\f5-tts\repo\ckpts\F5TTS_v1_Base\vocab.txt
```

Override the model and paths with `F5_MODEL`, `F5_CKPT_FILE`, `F5_VOCAB_FILE`, `F5TTS_REPO_DIR` or `F5TTS_PYTHON` when needed. The service fails at startup if the configured local checkpoint or vocabulary is missing; it does not download or silently select another checkpoint.

## Current behavior

- serves `/v1/health`
- serves `/v1/voices`
- serves `/v1/synthesize`
- serves `/v1/clone`
- serves `/v1/clone/{task_id}/status`
- reserves `/v1/synthesize/stream` and `/v1/design` with protocol `404`
- loads local vocoder cache first
- loads local checkpoint first
- stores cloned voice profiles under `services/f5tts-service/data/profiles` by default

Protocol endpoint overview:
- [bobogen-api-reference.md](..\..\docs\services\bobogen-api-reference.md)
