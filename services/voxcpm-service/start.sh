#!/usr/bin/env bash
# start.sh — VoxCPM2 Service 启动脚本（Linux / AutoDL）
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$(cd "$SERVICE_ROOT/../.." && pwd)"

MODEL_ID="${VOXCPM_MODEL_ID:-voxcpm2}"
PYTHON_EXE="${VOXCPM_PYTHON:-${SERVICE_ROOT}/.venv/bin/python}"
REPO_DIR="${VOXCPM_REPO_DIR:-${WORKSPACE_ROOT}/models/voxcpm/repo}"
MODEL_DIR="${VOXCPM_MODEL_DIR:-${WORKSPACE_ROOT}/models/voxcpm/checkpoints}"
CONFIG_PATH="${VOXCPM_CONFIG_PATH:-${MODEL_DIR}/config.json}"
MODEL_WEIGHTS_PATH="${VOXCPM_MODEL_WEIGHTS_PATH:-${MODEL_DIR}/model.safetensors}"
AUDIOVAE_WEIGHTS_PATH="${VOXCPM_AUDIOVAE_WEIGHTS_PATH:-${MODEL_DIR}/audiovae.pth}"
TOKENIZER_PATH="${VOXCPM_TOKENIZER_PATH:-${MODEL_DIR}/tokenizer.json}"
PROFILE_DIR="${VOXCPM_PROFILE_DIR:-${SERVICE_ROOT}/data/profiles/${MODEL_ID}}"
OUTPUT_DIR="${VOXCPM_OUTPUT_DIR:-${WORKSPACE_ROOT}/models/voxcpm/outputs/${MODEL_ID}}"
EXPECTED_ARCHITECTURE="${VOXCPM_EXPECTED_ARCHITECTURE:-voxcpm2}"
PORT="${VOXCPM_PORT:-5105}"
HOST="${VOXCPM_HOST:-127.0.0.1}"
REPO_SRC="${REPO_DIR}/src"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple"

if [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: VoxCPM repo not found at $REPO_DIR"
    echo "Run: git clone https://github.com/OpenBMB/VoxCPM.git $REPO_DIR"
    exit 1
fi
for required_path in "$MODEL_DIR" "$CONFIG_PATH" "$MODEL_WEIGHTS_PATH" "$AUDIOVAE_WEIGHTS_PATH" "$TOKENIZER_PATH"; do
    if [ ! -e "$required_path" ]; then
        echo "ERROR: required VoxCPM2 model file not found: $required_path"
        exit 1
    fi
done

# venv 不存在则用 uv sync 一键创建
if [ ! -f "$PYTHON_EXE" ]; then
    echo "[setup] venv 不存在，自动创建..."
    if ! command -v uv &>/dev/null; then
        pip install uv -q -i "$PIP_INDEX"
    fi
    cd "$REPO_DIR"
    uv sync --default-index "$PIP_INDEX"
    uv pip install uvicorn fastapi httpx pydantic pyyaml python-multipart --default-index "$PIP_INDEX"
    cd "$SERVICE_ROOT"
fi

mkdir -p "${PROFILE_DIR}/clones" "${PROFILE_DIR}/designs" "$OUTPUT_DIR"

cd "$SERVICE_ROOT"

export PYTHONPATH="${SERVICE_ROOT}:${WORKSPACE_ROOT}/bobogen-protocol/src:${WORKSPACE_ROOT}/bobogen-service-kit/src:${REPO_SRC}"
export VOXCPM_MODEL_ID="${MODEL_ID}"
export VOXCPM_REPO_DIR="${REPO_DIR}"
export VOXCPM_MODEL_DIR="${MODEL_DIR}"
export VOXCPM_CONFIG_PATH="${CONFIG_PATH}"
export VOXCPM_MODEL_WEIGHTS_PATH="${MODEL_WEIGHTS_PATH}"
export VOXCPM_AUDIOVAE_WEIGHTS_PATH="${AUDIOVAE_WEIGHTS_PATH}"
export VOXCPM_TOKENIZER_PATH="${TOKENIZER_PATH}"
export VOXCPM_PROFILE_DIR="${PROFILE_DIR}"
export VOXCPM_OUTPUT_DIR="${OUTPUT_DIR}"
export VOXCPM_EXPECTED_ARCHITECTURE="${EXPECTED_ARCHITECTURE}"
export VOXCPM_HOST="${HOST}"
export VOXCPM_PORT="${PORT}"
export VOXCPM_PRELOAD_ON_STARTUP="${VOXCPM_PRELOAD_ON_STARTUP:-true}"
export VOXCPM_LOAD_DENOISER="${VOXCPM_LOAD_DENOISER:-false}"
export VOXCPM_OPTIMIZE="${VOXCPM_OPTIMIZE:-false}"

echo "Using Python: $PYTHON_EXE"
echo "Model:        $VOXCPM_MODEL_ID"
echo "REPO:         $VOXCPM_REPO_DIR"
echo "MODEL:        $VOXCPM_MODEL_DIR"
echo "Architecture: $VOXCPM_EXPECTED_ARCHITECTURE"
echo "Preloading:   $VOXCPM_PRELOAD_ON_STARTUP"
echo "Starting voxcpm-service on http://${HOST}:${PORT}"

exec "$PYTHON_EXE" -m uvicorn app.main:create_app --factory --host "$HOST" --port "$PORT"
