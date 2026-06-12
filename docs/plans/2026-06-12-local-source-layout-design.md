# Local Source Layout Design

## Goal

Move GPT-SoVITS, F5-TTS, and CosyVoice integration toward the repository-local layout already used by IndexTTS2 and VoxCPM2, without installing model dependencies, downloading weights, or running real synthesis chain tests.

## Decision

Place upstream engine source checkouts under `models/<engine>/repo`:

- `models/gpt-sovits/repo`
- `models/f5-tts/repo`
- `models/cosyvoice/repo`

The `models/` directory is intentionally ignored by git, so the upstream repositories remain local machine assets. The service code and gateway configuration should reference these paths by default and still allow environment variable overrides for machines with different layouts.

## Architecture

Each protocol service remains the boundary between this repository and the upstream engine. The service `start.ps1` scripts compute the workspace root, set `PYTHONPATH` for shared protocol packages plus the engine source, and expose the standard FastAPI app through `local-tts-service-kit`.

The gateway keeps launching services through provider YAML files. For the three target engines, provider configs should start the local protocol services rather than invoking old external engine scripts directly.

## Verification Scope

Verification is limited to static and test-mode behavior:

- Provider config loading.
- Handler path resolution and environment overrides.
- Existing adapter request mapping.
- Test-mode FastAPI route behavior.

Out of scope for now:

- Installing upstream Python environments.
- Downloading model weights or Hugging Face caches.
- Starting real upstream inference.
- End-to-end audio chain testing through the gateway.
