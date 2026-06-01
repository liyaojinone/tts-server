#!/usr/bin/env bash
# start-gateway.sh — Local TTS Gateway 启动脚本（Linux / AutoDL）
#   bash start-gateway.sh         前台运行
#   bash start-gateway.sh -d       后台运行
#   bash start-gateway.sh --logs   查看日志
set -euo pipefail

GATEWAY_DIR="$(cd "$(dirname "$0")/local-tts-gateway" && pwd)"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple"
PORT="${1:-6006}"
DAEMON=false

case "${1:-}" in
    -d|--daemon)
        DAEMON=true
        PORT="${2:-6006}"
        ;;
    --logs|--log)
        tail -f "$GATEWAY_DIR/logs/gateway.log" 2>/dev/null || echo "No gateway log found yet"
        exit 0
        ;;
esac

cd "$GATEWAY_DIR"

echo "[setup] 检查并安装 Gateway 依赖..."
pip install fastapi httpx pydantic pyyaml uvicorn python-multipart -q -i "$PIP_INDEX"

mkdir -p logs
GATEWAY_LOG="$GATEWAY_DIR/logs/gateway.log"

if $DAEMON; then
    echo "Starting Gateway in background on http://0.0.0.0:$PORT"
    nohup python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" \
        >> "$GATEWAY_LOG" 2>&1 &
    echo "PID: $!"
    echo "Logs: $GATEWAY_LOG"
    echo "Check: curl http://127.0.0.1:$PORT/v1/health"
else
    echo "Starting Local TTS Gateway on http://0.0.0.0:$PORT"
    echo "Providers loaded from configs/providers/"
    echo ""
    exec python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT"
fi
