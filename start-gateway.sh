#!/usr/bin/env bash
# start-gateway.sh — Local TTS Gateway 启动脚本（Linux / AutoDL）
# 使用前请先启动各项引擎服务（如 bash services/index-tts-service/start.sh）
set -euo pipefail

GATEWAY_DIR="$(cd "$(dirname "$0")/local-tts-gateway" && pwd)"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple"
PORT="${1:-6006}"

cd "$GATEWAY_DIR"

# 自动安装依赖
if ! python3 -c "import fastapi, httpx, pydantic, yaml, uvicorn" 2>/dev/null; then
    echo "[setup] 安装 Gateway 依赖..."
    pip install fastapi httpx pydantic pyyaml uvicorn python-multipart -q -i "$PIP_INDEX"
fi

echo "Starting Local TTS Gateway on http://0.0.0.0:$PORT"
echo "Providers loaded from configs/providers/"
echo ""

exec python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT"
