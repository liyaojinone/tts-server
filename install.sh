#!/usr/bin/env bash
# install.sh — Local TTS Server 一键安装（Linux / Git Bash）
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}>> $1${NC}"; }
ok()   { echo -e "   ${GREEN}OK${NC} — $1"; }
warn() { echo -e "   ${YELLOW}WARN${NC} — $1"; }

echo ""
echo "========================================"
echo "  Local TTS Server — 环境安装"
echo "========================================"
echo ""

# ---- 环境检查 ----
step "检查基础环境"
if ! command -v git &>/dev/null; then echo "请先安装 git"; exit 1; fi
if ! command -v python3 &>/dev/null; then echo "请先安装 python3"; exit 1; fi
ok "git & python3 就绪"

# 系统音频库（Linux 专有）
_PLATFORM="$(uname -s 2>/dev/null || echo "Unknown")"
if [ "$_PLATFORM" = "Linux" ]; then
    if ! python3 -c "import soundfile; soundfile.SoundFile('/dev/null')" 2>/dev/null; then
        echo "   安装系统音频库..."
        apt-get update -qq && apt-get install -y -qq libsndfile1 2>/dev/null || \
        conda install -y -c conda-forge libsndfile 2>/dev/null || true
    fi
    ok "系统依赖就绪"
fi

# uv 包管理器
if ! command -v uv &>/dev/null; then
    echo "   安装 uv..."
    pip install uv
fi
ok "uv 就绪"

PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple}"

# ---- 模型选择 ----
echo ""
echo -e "${YELLOW}请选择要安装的模型：${NC}"
echo ""
echo "  1. IndexTTS2  — 参考音频驱动 + emotion control"
echo "  2. VoxCPM2    — 文本指令驱动，无需参考音频"
echo "  a. 全部"
echo "  q. 跳过（仅安装 Gateway 依赖）"
echo ""
read -rp "输入序号（多选用空格分隔，如 1 2）：" choice

case "$choice" in
    q|Q) models="" ;;
    a|A) models="indextts voxcpm" ;;
    *)  models=""
        for c in $choice; do
            case $c in
                1) models="$models indextts" ;;
                2) models="$models voxcpm" ;;
            esac
        done ;;
esac

if [ -n "$models" ]; then
    echo ""
    echo "已选择: $models"
fi

# ---- 逐个初始化模型 ----
for model in $models; do
    case $model in
        indextts)
            NAME="IndexTTS2"
            REPO_URL="https://github.com/index-tts/index-tts.git"
            REPO_DIR="models/index-tts/repo"
            WEIGHTS_MODELSCOPE="IndexTeam/IndexTTS-2"
            WEIGHTS_DIR="models/index-tts/checkpoints"
            VENV_DIR="$REPO_DIR/.venv"
            SERVICE_DEPS="uvicorn fastapi httpx pydantic pyyaml python-multipart"
            ;;
        voxcpm)
            NAME="VoxCPM2"
            REPO_URL="https://github.com/OpenBMB/VoxCPM.git"
            REPO_DIR="models/voxcpm/repo"
            WEIGHTS_MODELSCOPE="OpenBMB/VoxCPM"
            WEIGHTS_DIR="models/voxcpm/checkpoints"
            VENV_DIR="services/voxcpm-service/.venv"
            SERVICE_DEPS="uvicorn fastapi httpx pydantic pyyaml python-multipart"
            ;;
    esac

    echo ""
    echo "========================================"
    echo "  $NAME"
    echo "========================================"

    # 1. 克隆仓库
    step "1/3 源码仓库"
    if [ -d "$REPO_DIR/.git" ]; then
        ok "仓库已存在: $REPO_DIR"
    else
        echo "   git clone $REPO_URL -> $REPO_DIR"
        mkdir -p "$(dirname "$REPO_DIR")"
        git clone "$REPO_URL" "$REPO_DIR"
        ok "克隆完成"
    fi

    # 2. 下载模型权重
    step "2/3 模型权重"
    if [ -d "$WEIGHTS_DIR" ] && [ "$(find "$WEIGHTS_DIR" -type f \( -name '*.pth' -o -name '*.safetensors' -o -name '*.pt' \) 2>/dev/null | wc -l)" -gt 0 ]; then
        ok "权重已存在: $WEIGHTS_DIR ($(find "$WEIGHTS_DIR" -type f | wc -l) 个文件)"
    else
        mkdir -p "$WEIGHTS_DIR"
        if ! python3 -c "import modelscope" 2>/dev/null; then
            pip install modelscope -q -i "$PIP_INDEX"
        fi
        echo "   modelscope download --model $WEIGHTS_MODELSCOPE"
        modelscope download --model "$WEIGHTS_MODELSCOPE" --local_dir "$WEIGHTS_DIR"
        ok "下载完成（ModelScope）"
    fi

    # 3. 虚拟环境
    step "3/3 Python 虚拟环境"
    echo "   cd $REPO_DIR && uv sync --default-index $PIP_INDEX"
    mkdir -p "$(dirname "$VENV_DIR")"
    ( cd "$REPO_DIR" && uv sync --default-index "$PIP_INDEX" )
    ok "venv 就绪（uv sync）"

    echo "   uv pip install $SERVICE_DEPS"
    ( cd "$REPO_DIR" && uv pip install $SERVICE_DEPS --default-index "$PIP_INDEX" )
    ok "服务层依赖就绪"
done

# ---- 外部引擎检查 ----
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

# ---- Gateway 依赖 ----
step "Gateway 依赖"
pip install fastapi httpx pydantic pyyaml uvicorn python-multipart mcp -q -i "$PIP_INDEX"
ok "Gateway 依赖就绪"

echo ""
echo "========================================"
echo -e "  ${GREEN}安装完成！${NC}"
echo "========================================"
echo ""
echo "下一步："
echo "  bash start.sh        前台启动 Gateway"
echo "  bash start.sh -d     后台启动 Gateway"
echo "  bash start.sh --logs 查看日志"
