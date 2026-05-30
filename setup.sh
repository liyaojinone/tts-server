#!/usr/bin/env bash
# setup.sh — Local TTS Server 模型环境初始化（Linux / AutoDL）
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}>> $1${NC}"; }
ok()   { echo -e "   ${GREEN}OK${NC} — $1"; }
warn() { echo -e "   ${YELLOW}WARN${NC} — $1"; }
err()  { echo -e "   ${RED}ERR${NC} — $1"; }

echo ""
echo "========================================"
echo "  Local TTS Server - 模型环境初始化"
echo "========================================"
echo ""

# ---------- 模型选择 ----------
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

# ---------- 基础检查 ----------
step "检查基础环境"
if ! command -v git &>/dev/null; then echo "请先安装 git"; exit 1; fi
if ! command -v python3 &>/dev/null; then echo "请先安装 python3"; exit 1; fi
ok "git & python3 就绪"

# HF 镜像
if [ -z "${HF_ENDPOINT:-}" ]; then
    read -rp "是否使用 HF 镜像 hf-mirror.com？（国内推荐 y/n）：" hf
    if [ "$hf" = "y" ]; then
        export HF_ENDPOINT="https://hf-mirror.com"
        ok "已设置 HF_ENDPOINT=https://hf-mirror.com"
    fi
fi

# ---------- 逐个初始化 ----------
for model in $models; do
    case $model in
        indextts)
            NAME="IndexTTS2"
            REPO_URL="https://github.com/index-tts/index-tts.git"
            REPO_DIR="models/index-tts/repo"
            WEIGHTS_REPO="IndexTeam/IndexTTS"
            WEIGHTS_DIR="models/index-tts/checkpoints"
            VENV_DIR="models/index-tts/repo/.venv"
            PIP_DEPS="huggingface_hub soundfile librosa torch torchaudio transformers modelscope safetensors omegaconf"
            ;;
        voxcpm)
            NAME="VoxCPM2"
            REPO_URL="https://github.com/OpenBMB/VoxCPM.git"
            REPO_DIR="models/voxcpm/repo"
            WEIGHTS_REPO="OpenBMB/VoxCPM"
            WEIGHTS_DIR="models/voxcpm/checkpoints"
            VENV_DIR="services/voxcpm-service/.venv"
            PIP_DEPS="huggingface_hub soundfile torch torchaudio transformers safetensors omegaconf hydra-core"
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

    # 2. 下载权重
    step "2/3 模型权重"
    if [ -d "$WEIGHTS_DIR" ] && ls "$WEIGHTS_DIR"/*.safetensors &>/dev/null 2>&1; then
        ok "权重已存在: $WEIGHTS_DIR"
    elif [ -d "$WEIGHTS_DIR" ] && [ "$(find "$WEIGHTS_DIR" -type f | wc -l)" -gt 0 ]; then
        ok "权重目录已存在（$(find "$WEIGHTS_DIR" -type f | wc -l) 个文件）"
    else
        if pip show huggingface_hub &>/dev/null; then
            echo "   huggingface-cli download $WEIGHTS_REPO --local-dir $WEIGHTS_DIR"
            mkdir -p "$WEIGHTS_DIR"
            huggingface-cli download "$WEIGHTS_REPO" --local-dir "$WEIGHTS_DIR"
            ok "下载完成"
        else
            warn "huggingface_hub 未安装，跳过。请手动下载："
            echo "     pip install huggingface_hub"
            echo "     huggingface-cli download $WEIGHTS_REPO --local-dir $WEIGHTS_DIR"
        fi
    fi

    # 3. 虚拟环境
    step "3/3 Python 虚拟环境"
    if [ -f "$VENV_DIR/bin/python" ]; then
        ok "venv 已存在: $VENV_DIR"
    else
        echo "   python3 -m venv $VENV_DIR"
        python3 -m venv "$VENV_DIR"
        ok "venv 创建完成"
    fi

    # 安装依赖
    if [ -f "$VENV_DIR/bin/pip" ] && [ -n "$PIP_DEPS" ]; then
        read -rp "   是否安装/更新 pip 依赖？（y/n，默认 n）" idp
        if [ "$idp" = "y" ]; then
            echo "   $VENV_DIR/bin/pip install $PIP_DEPS"
            "$VENV_DIR/bin/pip" install $PIP_DEPS
            ok "依赖安装完成"
        else
            warn "跳过依赖安装"
        fi
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
echo "下一步：运行对应 start.sh"
echo "  IndexTTS2 : ./services/index-tts-service/start.sh"
echo "  VoxCPM2   : ./services/voxcpm-service/start.sh"
