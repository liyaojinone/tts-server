# gptsovits-service

Protocol-compliant `GPT-SoVITS` service built on top of the shared local TTS packages.

## Install

Use the `GPT-SoVITS` environment, then install the shared packages:

```bash
pip install -e ..\..\local-tts-protocol
pip install -e ..\..\local-tts-service-kit
```

## Run

Run with the `GPT-SoVITS` Python environment:

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5103
```

Base URL:

```text
http://127.0.0.1:5103
```

Or just use the bundled script:

```powershell
.\start.ps1
```

By default `start.ps1` reads upstream source from `models\gpt-sovits\repo` and Python from `services\gptsovits-service\.venv\Scripts\python.exe`. Override with `GPTSOVITS_REPO_DIR` or `GPTSOVITS_PYTHON` when needed.

Windows double-click:

```text
start.bat
```

Health check:

```powershell
.\healthcheck.ps1
```

Clone and synthesize smoke test:

```powershell
.\clone-test.ps1
```

## Current behavior

- serves `/v1/health`
- serves `/v1/voices`
- serves `/v1/synthesize`
- serves `/v1/clone`
- serves `/v1/clone/{task_id}/status`
- reserves `/v1/synthesize/stream` and `/v1/design` with protocol `404`
- uses reference-driven GPT-SoVITS synthesis
- prefers local GPT and SoVITS weight directories
- stores cloned voice profiles under `services/gptsovits-service/data/profiles` by default

Protocol endpoint overview:
- [local-tts-service-endpoints.md](..\..\docs\services\local-tts-service-endpoints.md)

## Clone flow

`/v1/clone` creates a reusable voice profile from one reference audio file. The created `voice_id`
will appear in `/v1/voices` and can be used in `/v1/synthesize` without passing
`parameters.reference_audio` again.

Example:

```powershell
Invoke-WebRequest `
  -Uri "http://127.0.0.1:5103/v1/clone" `
  -Method POST `
  -Form @{
    audio = Get-Item "E:\path\to\reference.wav"
    name = "pangbai"
    text = "庞白参考文本"
    language = "zh"
    emotion = "calm"
  }
```

Then synthesize with:

```json
{
  "text": "你好，这是一次复用克隆音色的测试。",
  "voice_id": "pangbai",
  "language": "zh",
  "parameters": {},
  "output": {
    "format": "wav"
  }
}
```
