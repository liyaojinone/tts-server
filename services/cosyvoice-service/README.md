# cosyvoice-service

Protocol-compliant `CosyVoice` service built on top of the shared local TTS packages.

## Install

Use the `CosyVoice` environment, then install the shared packages:

```bash
pip install -e ..\..\bobogen-protocol
pip install -e ..\..\bobogen-service-kit
```

## Run

Run with the `CosyVoice` Python environment:

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5101
```

Base URL:

```text
http://127.0.0.1:5101
```

Or use the bundled scripts:

```powershell
.\start.ps1
.\healthcheck.ps1
.\clone-test.ps1
```

By default `start.ps1` reads upstream source from `models\cosyvoice\repo` and Python from `services\cosyvoice-service\.venv\Scripts\python.exe`. Override with `COSYVOICE_REPO_DIR` or `COSYVOICE_PYTHON` when needed.

## Current behavior

- serves `/v1/health`
- serves `/v1/voices`
- serves `/v1/synthesize`
- serves `/v1/clone`
- serves `/v1/clone/{task_id}/status`
- reserves `/v1/synthesize/stream` and `/v1/design` with protocol `404`
- supports preset SFT mode through `voice_id`
- supports zero-shot clone mode through `voice_id=clone`
- stores cloned voice profiles under `services/cosyvoice-service/data/profiles` by default

Protocol endpoint overview:
- [bobogen-api-reference.md](..\..\docs\services\bobogen-api-reference.md)
