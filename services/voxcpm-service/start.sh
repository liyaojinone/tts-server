#!/usr/bin/env bash
# start.sh — VoxCPM2 Service 启动脚本（Linux / AutoDL）
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$(cd "$SERVICE_ROOT/../.." && pwd)"

PYTHON_EXE="${SERVICE_ROOT}/.venv/bin/python"
REPO_DIR="${WORKSPACE_ROOT}/models/voxcpm/repo"
MODEL_DIR="${WORKSPACE_ROOT}/models/voxcpm/checkpoints"
PROFILE_DIR="${SERVICE_ROOT}/data/profiles"
OUTPUT_DIR="${WORKSPACE_ROOT}/models/voxcpm/outputs"
REPO_SRC="${REPO_DIR}/src"

if [ ! -f "$PYTHON_EXE" ]; then
    echo "ERROR: Python not found at $PYTHON_EXE"
    echo "Run setup.sh first to create the venv."
    exit 1
fi
if [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: VoxCPM repo not found at $REPO_DIR"
    exit 1
fi
if [ ! -d "$MODEL_DIR" ]; then
    echo "ERROR: Model checkpoints not found at $MODEL_DIR"
    exit 1
fi

mkdir -p "${PROFILE_DIR}/clones" "${PROFILE_DIR}/designs" "$OUTPUT_DIR"

cd "$SERVICE_ROOT"

export PYTHONPATH="${SERVICE_ROOT}:${WORKSPACE_ROOT}/local-tts-protocol/src:${WORKSPACE_ROOT}/local-tts-service-kit/src:${REPO_SRC}"
export VOXCPM_REPO_DIR="${REPO_DIR}"
export VOXCPM_MODEL_DIR="${MODEL_DIR}"
export VOXCPM_PROFILE_DIR="${PROFILE_DIR}"
export VOXCPM_OUTPUT_DIR="${OUTPUT_DIR}"
export VOXCPM_PRELOAD_ON_STARTUP="true"
export VOXCPM_LOAD_DENOISER="false"
export VOXCPM_OPTIMIZE="false"

echo "Using Python: $PYTHON_EXE"
echo "REPO:         $VOXCPM_REPO_DIR"
echo "MODEL:        $VOXCPM_MODEL_DIR"
echo "Preloading:   $VOXCPM_PRELOAD_ON_STARTUP"
echo "Starting voxcpm-service on http://0.0.0.0:5105"

exec "$PYTHON_EXE" -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 5105
