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
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple}"

# --- 环境自检 & 自动修复 ---
ensure_venv() {
    if ! command -v uv &>/dev/null; then
        echo "[setup] 安装 uv..."
        pip install uv -q -i "$PIP_INDEX" || true
    fi
    if [ ! -f "$PYTHON_EXE" ]; then
        echo "[setup] venv 不存在，自动创建..."
        mkdir -p "$(dirname "$PYTHON_EXE")"
        cd "$REPO_DIR"
        uv sync --default-index "$PIP_INDEX" || true
        cd "$SERVICE_ROOT"
    fi
    local missing=""
    for pkg in uvicorn fastapi httpx pydantic yaml soundfile safetensors omegaconf; do
        "$PYTHON_EXE" -c "import $pkg" 2>/dev/null || missing="$missing $pkg"
    done
    if [ -n "$missing" ]; then
        echo "[setup] 缺失依赖:$missing，自动安装..."
        cd "$REPO_DIR"
        uv pip install $missing uvicorn fastapi httpx pydantic pyyaml python-multipart --default-index "$PIP_INDEX" || true
        cd "$SERVICE_ROOT"
    fi
}

if [ ! -d "$REPO_DIR" ]; then
    echo "ERROR: VoxCPM repo not found at $REPO_DIR"
    echo "Run: git clone https://github.com/OpenBMB/VoxCPM.git $REPO_DIR"
    exit 1
fi
if [ ! -d "$MODEL_DIR" ]; then
    echo "ERROR: Model checkpoints not found at $MODEL_DIR"
    echo "Run: modelscope download --model OpenBMB/VoxCPM --local-dir $MODEL_DIR"
    exit 1
fi

ensure_venv

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
