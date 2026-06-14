#!/usr/bin/env bash
# start.sh - Stable Audio 3 Service 启动脚本（Linux / AutoDL）
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$(cd "$SERVICE_ROOT/../.." && pwd)"

REPO_DIR="${STABLE_AUDIO3_REPO_DIR:-${WORKSPACE_ROOT}/models/stable-audio-3/repo}"
CACHE_ROOT="${WORKSPACE_ROOT}/models/stable-audio-3"
PYTHON_EXE="${STABLE_AUDIO3_PYTHON:-${REPO_DIR}/.venv/bin/python}"
SHARED_PROTOCOL_SRC="${WORKSPACE_ROOT}/bobogen-protocol/src"

if [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: Stable Audio 3 repo not found: $REPO_DIR"
    echo "Run: git clone https://github.com/Stability-AI/stable-audio-3.git $REPO_DIR"
    exit 1
fi

if [ ! -x "$PYTHON_EXE" ]; then
    echo "ERROR: Python executable not found: $PYTHON_EXE"
    echo "Run: cd $REPO_DIR && uv sync && uv pip install fastapi uvicorn pydantic sentencepiece protobuf"
    exit 1
fi

mkdir -p "$CACHE_ROOT/hf-home" "$CACHE_ROOT/torch-cache"
cd "$SERVICE_ROOT"

export PYTHONPATH="${SERVICE_ROOT}:${SHARED_PROTOCOL_SRC}:${REPO_DIR}"
export STABLE_AUDIO3_REPO_DIR="$REPO_DIR"
export STABLE_AUDIO3_MODEL_NAME="${STABLE_AUDIO3_MODEL_NAME:-small-sfx}"
export UV_CACHE_DIR="${CACHE_ROOT}/uv-cache"
export PIP_CACHE_DIR="${CACHE_ROOT}/pip-cache"
export HF_HOME="${HF_HOME:-${CACHE_ROOT}/hf-home}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"
export TORCH_HOME="${TORCH_HOME:-${CACHE_ROOT}/torch-cache}"

echo "Using Python: $PYTHON_EXE"
echo "PYTHONPATH: $PYTHONPATH"
echo "Stable Audio 3 repo: $STABLE_AUDIO3_REPO_DIR"
echo "HF_HOME: $HF_HOME"
echo "Stable Audio 3 model: $STABLE_AUDIO3_MODEL_NAME"
echo "Stable Audio 3 test mode: ${STABLE_AUDIO3_TEST_MODE:-}"
echo "Starting stable-audio3-service on http://127.0.0.1:5106"

exec "$PYTHON_EXE" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5106
