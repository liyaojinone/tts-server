#!/usr/bin/env bash
# start.sh — IndexTTS2 Service 启动脚本（Linux / AutoDL）
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$(cd "$SERVICE_ROOT/../.." && pwd)"

PYTHON_EXE="${WORKSPACE_ROOT}/models/index-tts/repo/.venv/bin/python"
REPO_DIR="${WORKSPACE_ROOT}/models/index-tts/repo"
MODEL_DIR="${WORKSPACE_ROOT}/models/index-tts/checkpoints"
PROFILE_DIR="${SERVICE_ROOT}/data/profiles"
OUTPUT_DIR="${WORKSPACE_ROOT}/models/index-tts/outputs"

if [ ! -f "$PYTHON_EXE" ]; then
    echo "ERROR: Python not found at $PYTHON_EXE"
    echo "Run setup.sh first to create the venv."
    exit 1
fi
if [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: IndexTTS repo not found at $REPO_DIR"
    exit 1
fi
if [ ! -d "$MODEL_DIR" ]; then
    echo "ERROR: Model checkpoints not found at $MODEL_DIR"
    exit 1
fi

mkdir -p "$PROFILE_DIR" "$OUTPUT_DIR"

cd "$SERVICE_ROOT"

export PYTHONPATH="${SERVICE_ROOT}:${WORKSPACE_ROOT}/local-tts-protocol/src:${WORKSPACE_ROOT}/local-tts-service-kit/src:${REPO_DIR}"
export INDEXTTS_REPO_DIR="${REPO_DIR}"
export INDEXTTS_MODEL_DIR="${MODEL_DIR}"
export INDEXTTS_PROFILE_DIR="${PROFILE_DIR}"
export INDEXTTS_OUTPUT_DIR="${OUTPUT_DIR}"
export INDEXTTS_USE_FP16="true"
export INDEXTTS_USE_CUDA_KERNEL="true"
export INDEXTTS_USE_DEEPSPEED="false"
export INDEXTTS_USE_ACCEL="false"
export INDEXTTS_USE_TORCH_COMPILE="false"
export INDEXTTS_PRELOAD_ON_STARTUP="true"

echo "Using Python: $PYTHON_EXE"
echo "REPO:         $INDEXTTS_REPO_DIR"
echo "MODEL:        $INDEXTTS_MODEL_DIR"
echo "Preloading:   $INDEXTTS_PRELOAD_ON_STARTUP"
echo "Starting index-tts-service on http://0.0.0.0:5104"

exec "$PYTHON_EXE" -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 5104
