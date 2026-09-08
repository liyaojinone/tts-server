# Qwen3-ASR Service

Local GPU-only ASR service for `Qwen/Qwen3-ASR-0.6B` and `Qwen/Qwen3-ASR-1.7B`.

## Models

| Model ID | Hugging Face repo | Port |
|----------|-------------------|------|
| `qwen3_asr_0_6b` | `Qwen/Qwen3-ASR-0.6B` | `5110` |
| `qwen3_asr_1_7b` | `Qwen/Qwen3-ASR-1.7B` | `5111` |
| `qwen3_forced_aligner_0_6b` | `Qwen/Qwen3-ForcedAligner-0.6B-hf` | `5112` |

The service requires CUDA. CPU-only PyTorch is rejected at model load time.

## Setup

Clone the upstream repository into the shared `models/` tree, then create a dedicated service environment and install CUDA-enabled PyTorch before installing `qwen-asr` from that local source tree.

```powershell
New-Item -ItemType Directory -Force -Path models\qwen3-asr
git clone https://github.com/QwenLM/Qwen3-ASR.git models\qwen3-asr\repo
cd services/qwen3-asr-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -e ..\..\bobogen-protocol
.\.venv\Scripts\python.exe -m pip install -e ..\..\models\qwen3-asr\repo
.\.venv\Scripts\python.exe -m pip install -e .
```

The official local model directory is `models/qwen3-asr/repo/Qwen3-ASR-0.6B`, matching the upstream manual download command when run from the repository root. If that directory is complete, the service loads it without downloading. If `QWEN3_ASR_MODEL_DIR` is unset, the official model ID is used and the upstream `qwen-asr` loader may download through its configured Hugging Face/ModelScope mechanism.

For a Hugging Face mirror, set `QWEN3_ASR_HF_ENDPOINT` before starting the service. The start script passes it as the process-local `HF_ENDPOINT`; it does not change the user's persistent environment.

Forced Aligner 使用官方原生 Transformers token-classification 实现和独立环境，避免升级
Transformers 影响现有 ASR：

```powershell
cd services\qwen3-asr-service
python -m venv .venv-aligner
.\.venv-aligner\Scripts\python.exe -m pip install -U pip
.\.venv-aligner\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
.\.venv-aligner\Scripts\python.exe -m pip install -e ..\..\bobogen-protocol
.\.venv-aligner\Scripts\python.exe -m pip install -e ".[aligner]"
.\.venv-aligner\Scripts\python.exe -m pip install git+https://github.com/huggingface/transformers
```

## Run

Default 0.6B:

```powershell
.\start.ps1
```

Try 1.7B:

```powershell
$env:QWEN3_ASR_MODEL_ID = "qwen3_asr_1_7b"
$env:QWEN3_ASR_HF_REPO_ID = "Qwen/Qwen3-ASR-1.7B"
$env:QWEN3_ASR_PORT = "5111"
.\start.ps1
```

Run ForcedAligner:

```powershell
$env:QWEN3_ASR_MODEL_ID = "qwen3_forced_aligner_0_6b"
$env:QWEN3_ASR_HF_REPO_ID = "Qwen/Qwen3-ForcedAligner-0.6B-hf"
$env:QWEN3_ASR_PYTHON = ".\.venv-aligner\Scripts\python.exe"
$env:QWEN3_ASR_PORT = "5112"
.\start.ps1
```

## API

```bash
curl -sS -X POST http://127.0.0.1:5110/v1/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3_asr_0_6b",
    "task": "asr.transcribe",
    "input": {"audio": "E:/audio/demo.wav", "language": "auto"},
    "parameters": {"mode": "offline", "timestamps": false},
    "output": {"format": "json"}
  }'
```

Response:

```json
{
  "text": "...",
  "language": "Chinese",
  "duration_seconds": null,
  "segments": [],
  "model": "qwen3_asr_0_6b"
}
```

Alignment request:

```bash
curl -sS -X POST http://127.0.0.1:5112/v1/align \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3_forced_aligner_0_6b",
    "task": "audio.align",
    "input": {
      "audio": "E:/audio/line.wav",
      "text": "你终于来了。",
      "language": "Chinese",
      "clip_start": 120.0
    },
    "parameters": {"granularity": "word"},
    "output": {"format": "json"}
  }'
```
