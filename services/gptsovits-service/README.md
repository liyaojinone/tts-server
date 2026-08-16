# gptsovits-service

Protocol-compliant `GPT-SoVITS V2Pro` service (`model_id: gpt_sovits_v2pro`) built on top of the shared local TTS packages.

## Versioned runtime assets

The gateway configuration passes every runtime path explicitly. The default V2Pro bundle is isolated at:

```text
models/gpt-sovits/checkpoints/gpt_sovits_v2pro/
├── s1v3.ckpt
├── v2Pro/s2Gv2Pro.pth
├── chinese-roberta-wwm-ext-large/
├── chinese-hubert-base/
└── sv/pretrained_eres2netv2w24s4ep4.ckpt
```

`start.ps1` forwards these as `GPTSOVITS_GPT_WEIGHTS_PATH`, `GPTSOVITS_SOVITS_WEIGHTS_PATH`, `GPTSOVITS_BERT_BASE_PATH`, `GPTSOVITS_CNHUBERT_BASE_PATH`, and `GPTSOVITS_SV_WEIGHTS_PATH`. All five must exist; the service does not scan legacy `GPT_weights*` / `SoVITS_weights*` directories or silently fall back to another version. Profiles, synthesis outputs, and the generated runtime config are separated under `gpt_sovits_v2pro` as well.

## Install

Use the `GPT-SoVITS` environment, then install the shared packages:

```bash
pip install -e ..\..\bobogen-protocol
pip install -e ..\..\bobogen-service-kit
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

By default `start.ps1` reads upstream source from `models\gpt-sovits\repo`, V2Pro assets from `models\gpt-sovits\checkpoints\gpt_sovits_v2pro`, and Python from `services\gptsovits-service\.venv\Scripts\python.exe`. Override the explicit `GPTSOVITS_*` paths and `GPTSOVITS_PORT` when needed.

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
- reports `version: gpt_sovits_v2pro` from `/v1/health`
- requires the configured, version-matched local model bundle
- stores cloned voice profiles under `services/gptsovits-service/data/profiles/gpt_sovits_v2pro` by default
- writes transient synthesis output under `models/gpt-sovits/outputs/gpt_sovits_v2pro`

Protocol endpoint overview:
- [bobogen-api-reference.md](..\..\docs\services\bobogen-api-reference.md)

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
