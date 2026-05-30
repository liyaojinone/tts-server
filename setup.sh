#!/usr/bin/env bash
# setup.sh — Local TTS Server 模型环境初始化（Linux / AutoDL）
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}>> $1${NC}"; }
ok()   { echo -e "   ${GREEN}OK${NC} — $1"; }
warn() { echo -e "   ${YELLOW}WARN${NC} — $1"; }

echo ""
echo "========================================"
echo "  Local TTS Server - 模型环境初始化"
echo "========================================"
echo ""

# ---------- 环境检查 ----------
step "检查基础环境"
if ! command -v git &>/dev/null; then echo "请先安装 git"; exit 1; fi
if ! command -v python3 &>/dev/null; then echo "请先安装 python3"; exit 1; fi
ok "git & python3 就绪"

# 确保 uv 已安装
if ! command -v uv &>/dev/null; then
    echo "   安装 uv..."
    pip install uv
fi
ok "uv 就绪"

# pip index 默认走阿里云镜像（国内加速）
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple}"

# ---------- 模型选择 ----------
echo ""
echo -e "${YELLOW}请选择要初始化的模型：${NC}"
echo ""
echo "  1. IndexTTS2  — 参考音频驱动 + emotion control"
echo "  2. VoxCPM2    — 文本指令驱动，无需参考音频"
echo "  a. 全部"
echo "  q. 退出"
echo ""
read -rp "输入序号（多选用空格分隔，如 1 2）：" choice

case "$choice" in
    q|Q) echo "已取消。"; exit 0 ;;
    a|A) models="indextts voxcpm" ;;
    *)  models=""
        for c in $choice; do
            case $c in
                1) models="$models indextts" ;;
                2) models="$models voxcpm" ;;
            esac
        done ;;
esac

if [ -z "$models" ]; then
    echo "未选择任何模型，退出。"
    exit 0
fi
echo ""
echo "已选择: $models"

# ---------- 逐个初始化 ----------
for model in $models; do
    case $model in
        indextts)
            NAME="IndexTTS2"
            REPO_URL="https://github.com/index-tts/index-tts.git"
            REPO_DIR="models/index-tts/repo"
            WEIGHTS_MODELSCOPE="IndexTeam/IndexTTS-2"
            WEIGHTS_HF="IndexTeam/IndexTTS"
            WEIGHTS_DIR="models/index-tts/checkpoints"
            VENV_DIR="$REPO_DIR/.venv"
            SERVICE_DEPS="uvicorn fastapi httpx pydantic pyyaml"
            ;;
        voxcpm)
            NAME="VoxCPM2"
            REPO_URL="https://github.com/OpenBMB/VoxCPM.git"
            REPO_DIR="models/voxcpm/repo"
            WEIGHTS_MODELSCOPE="OpenBMB/VoxCPM"
            WEIGHTS_HF="OpenBMB/VoxCPM"
            WEIGHTS_DIR="models/voxcpm/checkpoints"
            VENV_DIR="services/voxcpm-service/.venv"
            SERVICE_DEPS="uvicorn fastapi httpx pydantic pyyaml"
            ;;
    esac

    echo ""
    echo "========================================"
    echo "  $NAME"
    echo "========================================"

    # ---- 1. 克隆源码仓库 ----
    step "1/3 源码仓库"
    if [ -d "$REPO_DIR/.git" ]; then
        ok "仓库已存在: $REPO_DIR"
    else
        echo "   git clone $REPO_URL -> $REPO_DIR"
        mkdir -p "$(dirname "$REPO_DIR")"
        git clone "$REPO_URL" "$REPO_DIR"
        ok "克隆完成"
    fi

    # ---- 2. 下载模型权重（modelscope 优先，国内快） ----
    step "2/3 模型权重"
    if [ -d "$WEIGHTS_DIR" ] && [ "$(find "$WEIGHTS_DIR" -type f -name '*.pth' -o -name '*.safetensors' -o -name '*.pt' 2>/dev/null | wc -l)" -gt 0 ]; then
        ok "权重已存在: $WEIGHTS_DIR ($(find "$WEIGHTS_DIR" -type f | wc -l) 个文件)"
    else
        mkdir -p "$WEIGHTS_DIR"
        if python3 -c "import modelscope" 2>/dev/null; then
            echo "   modelscope download --model $WEIGHTS_MODELSCOPE"
            modelscope download --model "$WEIGHTS_MODELSCOPE" --local_dir "$WEIGHTS_DIR"
            ok "下载完成（ModelScope）"
        else
            echo "   pip install modelscope -q"
            pip install modelscope -q -i "$PIP_INDEX"
            echo "   modelscope download --model $WEIGHTS_MODELSCOPE"
            modelscope download --model "$WEIGHTS_MODELSCOPE" --local_dir "$WEIGHTS_DIR"
            ok "下载完成（ModelScope）"
        fi
    fi

    # ---- 3. 虚拟环境（uv sync，遵循引擎官方 pyproject.toml） ----
    step "3/3 Python 虚拟环境"
    if [ -f "$VENV_DIR/bin/python" ]; then
        ok "venv 已存在: $VENV_DIR"
    else
        echo "   cd $REPO_DIR && uv sync --default-index $PIP_INDEX"
        mkdir -p "$(dirname "$VENV_DIR")"
        ( cd "$REPO_DIR" && uv sync --default-index "$PIP_INDEX" )
        ok "venv 创建完成（uv sync）"
    fi

    # 追加服务层依赖
    if [ -n "$SERVICE_DEPS" ]; then
        echo "   uv pip install $SERVICE_DEPS"
        ( cd "$REPO_DIR" && uv pip install $SERVICE_DEPS --default-index "$PIP_INDEX" )
        ok "服务层依赖就绪"
    fi
done

# ---------- 外部引擎检查 ----------
echo ""
step "外部引擎检查"
for engine in "CosyVoice2:CosyVoice2/CosyVoice" "F5-TTS:F5-TTS" "GPT-SoVITS:GPT-SoVITS-v2-240821"; do
    name="${engine%%:*}"
    path="${engine##*:}"
    if [ -d "$(pwd)/$path" ]; then
        ok "$name 已就绪: $path"
    else
        warn "$name 未找到，如需使用请手动安装到项目根目录"
    fi
done

echo ""
echo "========================================"
echo -e "  ${GREEN}初始化完成！${NC}"
echo "========================================"
echo ""
echo "下一步："
echo "  IndexTTS2 : bash services/index-tts-service/start.sh"
echo "  VoxCPM2   : bash services/voxcpm-service/start.sh"
