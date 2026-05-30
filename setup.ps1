# setup.ps1 — Local TTS Server 模型环境初始化
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir

# 模型定义
$models = [ordered]@{
    "indextts" = @{
        Name        = "IndexTTS2"
        Desc        = "参考音频驱动 + emotion control"
        RepoUrl     = "https://github.com/index-tts/index-tts.git"
        RepoDir     = "models/index-tts/repo"
        WeightsRepo = "IndexTeam/IndexTTS"
        WeightsDir  = "models/index-tts/checkpoints"
        VenvDir     = "models/index-tts/repo/.venv"
        VenvDeps    = @("huggingface_hub", "soundfile", "librosa", "torch", "torchaudio", "transformers", "modelscope", "safetensors", "omegaconf")
        Pip         = "models/index-tts/repo/.venv/Scripts/pip.exe"
    }
    "voxcpm" = @{
        Name        = "VoxCPM2"
        Desc        = "文本指令驱动，无需参考音频"
        RepoUrl     = "https://github.com/OpenBMB/VoxCPM.git"
        RepoDir     = "models/voxcpm/repo"
        WeightsRepo = "OpenBMB/VoxCPM"
        WeightsDir  = "models/voxcpm/checkpoints"
        VenvDir     = "services/voxcpm-service/.venv"
        VenvDeps    = @("huggingface_hub", "soundfile", "torch", "torchaudio", "transformers", "safetensors", "omegaconf", "hydra-core")
        Pip         = "services/voxcpm-service/.venv/Scripts/pip.exe"
    }
}

# 外部引擎（不在 models/ 下，只做存在性检查）
$externalEngines = @{
    "cosyvoice" = @{
        Name  = "CosyVoice2"
        Paths = @("CosyVoice2/CosyVoice", "E:\AiModel\tts\CosyVoice2\CosyVoice")
    }
    "f5tts" = @{
        Name  = "F5-TTS"
        Paths = @("F5-TTS", "E:\AiModel\tts\F5-TTS")
    }
    "gptsovits" = @{
        Name  = "GPT-SoVITS"
        Paths = @("GPT-SoVITS-v2-240821", "E:\AiModel\tts\GPT-SoVITS-v2-240821")
    }
}

# --- 工具函数 ---
function Test-CmdExists($cmd) {
    try { Get-Command $cmd -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-OK($msg) { Write-Host "   OK — $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "   SKIP — $msg" -ForegroundColor DarkYellow }
function Write-Warn($msg) { Write-Host "   WARN — $msg" -ForegroundColor Yellow }

# --- 标题 ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Local TTS Server - 模型环境初始化" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- 选择模型 ---
Write-Host "请选择要初始化的模型：" -ForegroundColor Yellow
Write-Host ""
$idx = 1
$keyMap = @{}
foreach ($key in $models.Keys) {
    $m = $models[$key]
    $keyMap["$idx"] = $key
    Write-Host "  $idx. $($m.Name) — $($m.Desc)" -ForegroundColor White
    $idx++
}
Write-Host "  a. 全部"
Write-Host "  q. 退出"
Write-Host ""

$choice = (Read-Host "输入序号（多选用逗号分隔，如 1,2）").Trim().ToLower()
if ($choice -eq "q") { Write-Host "已取消。"; Pop-Location; exit 0 }

$selectedKeys = @()
if ($choice -eq "a") {
    $selectedKeys = @($models.Keys)
} else {
    $choice -split "\s*,\s*" | ForEach-Object {
        if ($keyMap.ContainsKey($_)) { $selectedKeys += $keyMap[$_] }
    }
}

if ($selectedKeys.Count -eq 0) {
    Write-Host "未选择任何模型，退出。" -ForegroundColor Red
    Pop-Location
    exit 0
}

Write-Host ""
Write-Host "已选择: $($selectedKeys -join ', ')" -ForegroundColor White
Write-Host ""

# --- 环境检查 ---
Write-Step "检查基础环境"
if (-not (Test-CmdExists "git")) {
    Write-Host "git 未安装或不在 PATH 中，请先安装 Git。" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-OK "git 已就绪"

$pythonCmd = $null
if (Test-CmdExists "python") { $pythonCmd = "python" }
else { Write-Warn "python 不在 PATH，创建 venv 时会尝试搜索" }

$huggingfaceCmd = $null
if (Test-CmdExists "huggingface-cli") { $huggingfaceCmd = "huggingface-cli" }
else { Write-Warn "huggingface-cli 未安装，权重下载步骤将跳过" }

# --- 检查 HF 镜像 ---
$hfEndpoint = $env:HF_ENDPOINT
if (-not $hfEndpoint) {
    $useMirror = Read-Host "是否使用 HF 镜像 hf-mirror.com？（国内推荐，输入 y/n）"
    if ($useMirror.Trim().ToLower() -eq "y") {
        $env:HF_ENDPOINT = "https://hf-mirror.com"
        Write-OK "已设置 HF_ENDPOINT=https://hf-mirror.com"
    }
}

# --- 执行初始化 ---
foreach ($key in $selectedKeys) {
    $m = $models[$key]
    Write-Host "`n========================================" -ForegroundColor DarkCyan
    Write-Host "  $($m.Name)" -ForegroundColor DarkCyan
    Write-Host "========================================" -ForegroundColor DarkCyan

    # 1. 克隆仓库
    Write-Step "1/3 源码仓库"
    if (Test-Path $m.RepoDir) {
        Write-OK "仓库已存在: $($m.RepoDir)"
    } else {
        Write-Host "   git clone $($m.RepoUrl) -> $($m.RepoDir)"
        New-Item -ItemType Directory -Force -Path (Split-Path $m.RepoDir) | Out-Null
        git clone $m.RepoUrl $m.RepoDir
        Write-OK "克隆完成"
    }

    # 2. 下载权重
    Write-Step "2/3 模型权重"
    if ((Test-Path $m.WeightsDir) -and (Get-ChildItem $m.WeightsDir -Filter "*.safetensors" -File | Select-Object -First 1)) {
        Write-OK "权重已存在: $($m.WeightsDir)"
    } elseif (Test-Path $m.WeightsDir) {
        $fileCount = (Get-ChildItem $m.WeightsDir -Recurse -File | Measure-Object).Count
        Write-OK "权重目录已存在（$fileCount 个文件）"
    } else {
        if ($huggingfaceCmd) {
            Write-Host "   huggingface-cli download $($m.WeightsRepo) --local-dir $($m.WeightsDir)"
            New-Item -ItemType Directory -Force -Path $m.WeightsDir | Out-Null
            huggingface-cli download $m.WeightsRepo --local-dir $m.WeightsDir
            Write-OK "下载完成"
        } else {
            Write-Warn "huggingface-cli 不可用，跳过。请手动下载:"
            Write-Host "     huggingface-cli download $($m.WeightsRepo) --local-dir $($m.WeightsDir)"
        }
    }

    # 3. 虚拟环境
    Write-Step "3/3 Python 虚拟环境"
    if (Test-Path $m.VenvDir) {
        Write-OK "venv 已存在: $($m.VenvDir)"
    } else {
        if ($pythonCmd) {
            Write-Host "   python -m venv $($m.VenvDir)"
            & $pythonCmd -m venv $m.VenvDir
            Write-OK "venv 创建完成"
        } else {
            Write-Warn "python 不可用，请手动创建 venv:"
            Write-Host "     python -m venv $($m.VenvDir)"
        }
    }

    # 安装依赖（询问用户）
    if ((Test-Path $m.Pip) -and $m.VenvDeps.Count -gt 0) {
        $installDeps = Read-Host "   是否安装/更新 pip 依赖？（y/n，默认 n）"
        if ($installDeps.Trim().ToLower() -eq "y") {
            Write-Host "   $($m.Pip) install $($m.VenvDeps -join ' ')"
            & $m.Pip install $m.VenvDeps
            Write-OK "依赖安装完成"
        } else {
            Write-Skip "跳过依赖安装"
        }
    }
}

# --- 外部引擎检查 ---
Write-Host ""
Write-Step "外部引擎检查"
foreach ($key in $externalEngines.Keys) {
    $e = $externalEngines[$key]
    $found = $false
    foreach ($p in $e.Paths) {
        if (Test-Path $p) {
            Write-OK "$($e.Name) 已就绪: $p"
            $found = $true
            break
        }
    }
    if (-not $found) {
        Write-Warn "$($e.Name) 未找到，如需要使用请手动安装到项目根目录"
    }
}

# --- 完成 ---
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  初始化完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步：启动对应服务" -ForegroundColor Yellow
Write-Host "  IndexTTS2 : .\services\index-tts-service\start.ps1"
Write-Host "  VoxCPM2   : .\services\voxcpm-service\start.ps1"
Write-Host "  Gateway   : cd local-tts-gateway && python -m uvicorn app.main:create_app --factory"

Pop-Location
