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

## Native Install

When disk space is available:

```bash
cd models/stable-audio-3/repo
uv sync
uv pip install fastapi uvicorn pydantic sentencepiece protobuf
huggingface-cli login
```

Accept the `stabilityai/stable-audio-3-small-sfx` terms on Hugging Face before running real inference.

Linux / AutoDL users can also run the repository installer and select Stable Audio 3:

```bash
bash install.sh
bash start.sh -d
bash start.sh --status
```

The service itself can be started directly:

```bash
bash services/stable-audio3-service/start.sh
```

## Docker

Docker Compose starts only the Gateway by default. Start Stable Audio 3 when needed:

```bash
bash start.sh --docker -d
bash start.sh --docker --model stable-audio3
```

This is equivalent to:

```bash
docker compose up -d gateway
docker compose --profile stable-audio3 up -d stable-audio3
```

The Docker image does not include gated model weights. Accept the Hugging Face model terms first, then provide `HF_TOKEN` or log in with `huggingface-cli login`. Runtime weights and caches are mounted under `models/stable-audio-3/` on the host.

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
