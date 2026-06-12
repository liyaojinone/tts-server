# stable-audio3-service

Protocol service for `stabilityai/stable-audio-3-small-sfx` through the BoboVox unified generation API.

## Source Layout

The official source repository is expected at:

```text
models/stable-audio-3/repo
```

Clone source only:

```bash
git clone https://github.com/Stability-AI/stable-audio-3.git models/stable-audio-3/repo
```

Model weights are gated on Hugging Face and are not downloaded by this repository.

## Install Later

When disk space is available:

```bash
cd models/stable-audio-3/repo
uv sync
huggingface-cli login
```

Accept the `stabilityai/stable-audio-3-small-sfx` terms on Hugging Face before running real inference.

## Endpoints

- `GET /v1/health`
- `POST /v1/generate`

Only `task = "audio.generate"` is supported.

```json
{
  "model": "stable-audio-3-small-sfx",
  "task": "audio.generate",
  "input": {"prompt": "short cinematic whoosh impact"},
  "parameters": {"duration": 7, "seed": 1234},
  "output": {"format": "wav", "sample_rate": 44100}
}
```
