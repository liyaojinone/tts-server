$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipIndex = if ($env:PIP_INDEX) { $env:PIP_INDEX } else { "https://mirrors.aliyun.com/pypi/simple" }

function Step($message) { Write-Host "`n>> $message" -ForegroundColor Cyan }
function Ok($message) { Write-Host "   OK - $message" -ForegroundColor Green }
function Warn($message) { Write-Host "   WARN - $message" -ForegroundColor Yellow }

Set-Location $root

Write-Host ""
Write-Host "========================================"
Write-Host "  BoboGen Server - Windows 环境安装"
Write-Host "========================================"
Write-Host ""

Step "检查基础环境"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "请先安装 git" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "请先安装 Python 3.10+" }
Ok "git & python 就绪"

Step "Gateway 依赖"
python -m pip install fastapi httpx pydantic pyyaml uvicorn python-multipart mcp -q -i $pipIndex
Ok "Gateway 依赖就绪"

Write-Host ""
Write-Host "请选择要安装的模型："
Write-Host ""
Write-Host "  1. Stable Audio 3 Small-SFX - 文本生成音效（Hugging Face gated 权重）"
Write-Host "  q. 跳过（仅安装 Gateway 依赖）"
Write-Host ""
$choice = Read-Host "输入序号"

if ($choice -eq "1") {
    $repoDir = Join-Path $root "models\stable-audio-3\repo"
    Step "Stable Audio 3 源码仓库"
    if (Test-Path (Join-Path $repoDir ".git")) {
        Ok "仓库已存在: $repoDir"
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $repoDir) | Out-Null
        git clone https://github.com/Stability-AI/stable-audio-3.git $repoDir
        Ok "克隆完成"
    }

    Step "Stable Audio 3 Python 环境"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        python -m pip install uv -q -i $pipIndex
    }
    Push-Location $repoDir
    uv sync
    uv pip install fastapi uvicorn pydantic sentencepiece protobuf
    Pop-Location
    Ok "Stable Audio 3 依赖就绪"

    Step "Hugging Face 权重授权"
    Warn "本脚本不会自动下载 gated 权重；请先接受 stabilityai/stable-audio-3-small-sfx 条款"
    if ($env:HF_TOKEN) {
        Ok "检测到 HF_TOKEN，首次生成时会下载权重"
    } elseif (Get-Command huggingface-cli -ErrorAction SilentlyContinue) {
        Warn "真实推理前请确认已登录: huggingface-cli login"
    } else {
        Warn "真实推理前请安装/登录 Hugging Face CLI: huggingface-cli login"
    }
}

Write-Host ""
Write-Host "安装完成。下一步："
Write-Host "  .\start.ps1 -Daemon"
Write-Host "  .\start.ps1 -Docker -Daemon"
