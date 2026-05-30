# f5tts-service

Protocol-compliant `F5-TTS` service built on top of the shared local TTS packages.

## Install

Use the `F5-TTS` environment, then install the shared packages:

```bash
pip install -e E:\AiModel\tts\local-tts-protocol
pip install -e E:\AiModel\tts\local-tts-service-kit
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
- [local-tts-service-endpoints.md](E:\AiModel\tts\docs\services\local-tts-service-endpoints.md)
