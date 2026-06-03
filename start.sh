#!/usr/bin/env bash
# start.sh — Local TTS Server 启动脚本
set -euo pipefail

usage() {
    echo ""
    echo "========================================="
    echo "  Local TTS Server — 运维控制"
    echo "========================================="
    echo ""
    echo "用法: bash start.sh [选项]"
    echo ""
    echo "启动:"
    echo "  (无参数)           前台启动 Gateway（调试用）"
    echo "  -d, --daemon       后台启动 Gateway（生产用）"
    echo "  -p, --port PORT    指定端口，默认 6006"
    echo ""
    echo "运维:"
    echo "  --status           查看所有引擎运行状态"
    echo "  --logs             实时查看 Gateway 日志"
    echo "  --stop             停止所有服务"
    echo "  --help             显示此帮助"
    echo ""
    echo "典型流程:"
    echo "  bash start.sh -d          # 后台启动 Gateway"
    echo "  bash start.sh --status    # 查看引擎是否就绪"
    echo "  bash start.sh --logs      # 查看运行日志"
    echo "  bash start.sh --stop      # 停止服务"
    echo ""
    echo "引擎通过 API 管理："
    echo "  curl http://127.0.0.1:6006/local_index_tts/v1/health"
    echo "  curl -X POST http://127.0.0.1:6006/local_index_tts/v1/providers/local_index_tts/start"
    echo ""
    exit 0
}

GATEWAY_DIR="$(cd "$(dirname "$0")/local-tts-gateway" && pwd)"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple"
PORT="6006"
DAEMON=false
ACTION="start"

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage ;;
        -d|--daemon)  DAEMON=true; shift ;;
        -p|--port)    PORT="$2"; shift 2 ;;
        --logs|--log) ACTION="logs"; shift ;;
        --status)     ACTION="status"; shift ;;
        --stop)       ACTION="stop"; shift ;;
        *)            echo "未知参数: $1，使用 --help 查看帮助"; exit 1 ;;
    esac
done

cd "$GATEWAY_DIR"

# ---- 日志查看 ----
if [ "$ACTION" = "logs" ]; then
    tail -f "$GATEWAY_DIR/logs/gateway.log" 2>/dev/null || echo "暂无 Gateway 日志"
    exit 0
fi

# ---- 停服 ----
if [ "$ACTION" = "stop" ]; then
    echo "正在停止所有服务..."
    curl -s -X POST "http://127.0.0.1:$PORT/local_index_tts/v1/providers/local_index_tts/stop" 2>/dev/null || true
    pkill -f "uvicorn app.main" 2>/dev/null || true
    echo "已停止"
    exit 0
fi

# ---- 状态查询 ----
if [ "$ACTION" = "status" ]; then
    curl -s "http://127.0.0.1:$PORT/local_index_tts/v1/providers/status" 2>/dev/null | python3 -m json.tool 2>/dev/null || \
      echo "Gateway 未启动或不可达"
    exit 0
fi

# ---- 启动 ----
echo "[setup] 检查并安装 Gateway 依赖..."
pip install fastapi httpx pydantic pyyaml uvicorn python-multipart mcp -q -i "$PIP_INDEX"

mkdir -p logs
GATEWAY_LOG="$GATEWAY_DIR/logs/gateway.log"

if $DAEMON; then
    echo "Gateway 后台启动: http://0.0.0.0:$PORT"
    nohup python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" \
        >> "$GATEWAY_LOG" 2>&1 &
    echo "PID: $!"
    echo "日志: $GATEWAY_LOG"
    echo "状态: curl http://127.0.0.1:$PORT/v1/health"
    echo "引擎: curl http://127.0.0.1:$PORT/local_index_tts/v1/providers/status"
else
    echo "Local TTS Gateway → http://0.0.0.0:$PORT"
    echo "引擎通过 API 管理，无需手动启动服务进程"
    echo ""
    exec python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT"
fi
