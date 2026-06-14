#!/usr/bin/env bash
# start.sh - BoboGen Server 启动脚本
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATEWAY_DIR="$ROOT_DIR/bobogen-gateway"
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple}"
PORT="${BOBOGEN_GATEWAY_PORT:-6006}"
DAEMON=false
DOCKER_MODE=false
MODEL=""
ACTION="start"

usage() {
    echo ""
    echo "========================================="
    echo "  BoboGen Server - 运维控制"
    echo "========================================="
    echo ""
    echo "用法: bash start.sh [选项]"
    echo ""
    echo "原生启动:"
    echo "  (无参数)              前台启动 Gateway（调试用）"
    echo "  -d, --daemon          后台启动 Gateway（生产用）"
    echo "  -p, --port PORT       指定端口，默认 6006"
    echo ""
    echo "Docker 启动:"
    echo "  --docker -d           后台启动 Gateway 容器"
    echo "  --docker --model stable-audio3"
    echo "                        按需启动 Stable Audio 3 容器"
    echo "                        等价: docker compose --profile stable-audio3 up -d stable-audio3"
    echo ""
    echo "运维:"
    echo "  --status              查看所有引擎运行状态"
    echo "  --logs                实时查看 Gateway 日志"
    echo "  --stop                停止服务"
    echo "  --help                显示此帮助"
    echo ""
    echo "典型流程:"
    echo "  bash start.sh -d"
    echo "  bash start.sh --docker -d"
    echo "  bash start.sh --docker --model stable-audio3"
    echo "  curl -X POST http://127.0.0.1:6006/v1/providers/stable_audio_3_small_sfx/start"
    echo ""
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage ;;
        -d|--daemon)  DAEMON=true; shift ;;
        -p|--port)    PORT="$2"; shift 2 ;;
        --docker)     DOCKER_MODE=true; shift ;;
        --model)      MODEL="$2"; shift 2 ;;
        --logs|--log) ACTION="logs"; shift ;;
        --status)     ACTION="status"; shift ;;
        --stop)       ACTION="stop"; shift ;;
        *)            echo "未知参数: $1，使用 --help 查看帮助"; exit 1 ;;
    esac
done

compose_service_for_model() {
    case "$1" in
        stable-audio3|stableaudio3|stable_audio3)
            echo "stable-audio3"
            ;;
        *)
            echo "未知模型: $1，目前 Docker v1 支持 stable-audio3" >&2
            exit 1
            ;;
    esac
}

run_docker() {
    cd "$ROOT_DIR"

    if [ -n "$MODEL" ]; then
        local service
        service="$(compose_service_for_model "$MODEL")"
        echo "Docker 按需启动模型: $service"
        docker compose --profile "$service" up -d "$service"
        exit 0
    fi

    case "$ACTION" in
        logs)
            docker compose logs -f gateway
            ;;
        stop)
            docker compose --profile stable-audio3 down
            ;;
        status)
            docker compose ps
            curl -s "http://127.0.0.1:$PORT/v1/providers/status" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
            ;;
        start)
            echo "Docker 启动 Gateway: http://127.0.0.1:$PORT"
            docker compose up -d gateway
            echo "状态: curl http://127.0.0.1:$PORT/v1/health"
            echo "模型: bash start.sh --docker --model stable-audio3"
            ;;
    esac
}

run_native() {
    cd "$GATEWAY_DIR"

    case "$ACTION" in
        logs)
            tail -f "$GATEWAY_DIR/logs/gateway.log" 2>/dev/null || echo "暂无 Gateway 日志"
            exit 0
            ;;
        stop)
            echo "正在停止服务..."
            for provider in stable_audio_3_small_sfx local_index_tts local_voxcpm local_gpt_sovits local_f5_tts local_cosyvoice2; do
                curl -s -X POST "http://127.0.0.1:$PORT/v1/providers/$provider/stop" >/dev/null 2>&1 || true
            done
            pkill -f "uvicorn app.main" 2>/dev/null || true
            echo "已停止"
            exit 0
            ;;
        status)
            curl -s "http://127.0.0.1:$PORT/v1/providers/status" 2>/dev/null | python3 -m json.tool 2>/dev/null || \
              echo "Gateway 未启动或不可达"
            exit 0
            ;;
    esac

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
        echo "引擎: curl http://127.0.0.1:$PORT/v1/providers/status"
    else
        echo "BoboGen Gateway -> http://0.0.0.0:$PORT"
        echo "引擎通过 API 管理，无需手动启动服务进程"
        echo ""
        exec python3 -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT"
    fi
}

if $DOCKER_MODE; then
    run_docker
else
    run_native
fi
