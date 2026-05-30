# setup.ps1 — Local TTS Server 模型环境初始化（Windows）
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir

$models = [ordered]@{
    "indextts" = @{
        Name           = "IndexTTS2"
        Desc           = "参考音频驱动 + emotion control"
        RepoUrl        = "https://github.com/index-tts/index-tts.git"
        RepoDir        = "models/index-tts/repo"
        WeightsSource  = "IndexTeam/IndexTTS-2"
        WeightsDir     = "models/index-tts/checkpoints"
        VenvDir        = "models/index-tts/repo/.venv"
        ServiceDeps    = @("uvicorn", "fastapi", "httpx", "pydantic", "pyyaml", "python-multipart")
        Pip            = "models/index-tts/repo/.venv/Scripts/pip.exe"
    }
    "voxcpm" = @{
        Name           = "VoxCPM2"
        Desc           = "文本指令驱动，无需参考音频"
        RepoUrl        = "https://github.com/OpenBMB/VoxCPM.git"
        RepoDir        = "models/voxcpm/repo"
        WeightsSource  = "OpenBMB/VoxCPM"
        WeightsDir     = "models/voxcpm/checkpoints"
        VenvDir        = "services/voxcpm-service/.venv"
        ServiceDeps    = @("uvicorn", "fastapi", "httpx", "pydantic", "pyyaml", "python-multipart")
        Pip            = "services/voxcpm-service/.venv/Scripts/pip.exe"
    }
}

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-OK($msg) { Write-Host "   OK — $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "   SKIP — $msg" -ForegroundColor DarkYellow }
function Write-Warn($msg) { Write-Host "   WARN — $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Local TTS Server - 模型环境初始化" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 环境检查
Write-Step "检查基础环境"
if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Host "git 未安装，请先安装 Git。" -ForegroundColor Red
    Pop-Location; exit 1
}
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "python 未安装，请先安装 Python。" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-OK "git & python 就绪"

# 模型选择
Write-Host ""
Write-Host "请选择要初始化的模型：" -ForegroundColor Yellow
Write-Host ""
$keyMap = @{}
$idx = 1
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
    Pop-Location; exit 0
}
Write-Host ""
Write-Host "已选择: $($selectedKeys -join ', ')" -ForegroundColor White

# 逐个初始化
foreach ($key in $selectedKeys) {
    $m = $models[$key]
    Write-Host "`n========================================" -ForegroundColor DarkCyan
    Write-Host "  $($m.Name)" -ForegroundColor DarkCyan
    Write-Host "========================================" -ForegroundColor DarkCyan

    # 1. 克隆仓库
    Write-Step "1/3 源码仓库"
    if (Test-Path "$($m.RepoDir)/.git") {
        Write-OK "仓库已存在: $($m.RepoDir)"
    } else {
        Write-Host "   git clone $($m.RepoUrl) -> $($m.RepoDir)"
        New-Item -ItemType Directory -Force -Path (Split-Path $m.RepoDir) | Out-Null
        git clone $m.RepoUrl $m.RepoDir
        Write-OK "克隆完成"
    }

    # 2. 下载权重
    Write-Step "2/3 模型权重"
    $weightFiles = Get-ChildItem -Path $m.WeightsDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in ".pth", ".safetensors", ".pt" }
    if ($weightFiles) {
        Write-OK "权重已存在: $($m.WeightsDir) ($($weightFiles.Count) 个文件)"
    } elseif (Test-Path $m.WeightsDir) {
        $fileCount = (Get-ChildItem -Path $m.WeightsDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-OK "权重目录已存在（$fileCount 个文件）"
    } else {
        New-Item -ItemType Directory -Force -Path $m.WeightsDir | Out-Null
        try {
            python -c "import modelscope" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   modelscope download --model $($m.WeightsSource)"
                modelscope download --model $m.WeightsSource --local_dir $m.WeightsDir
                Write-OK "下载完成（ModelScope）"
            }
        } catch {
            Write-Warn "modelscope 不可用，请手动下载："
            Write-Host "     pip install modelscope"
            Write-Host "     modelscope download --model $($m.WeightsSource) --local_dir $($m.WeightsDir)"
        }
    }

    # 3. 虚拟环境
    Write-Step "3/3 Python 虚拟环境 + 依赖"
    if (Test-Path $m.VenvDir) {
        Write-OK "venv 已存在: $($m.VenvDir)"
    } else {
        Write-Host "   cd $($m.RepoDir) && uv sync"
        Push-Location $m.RepoDir
        try {
            uv sync
            uv pip install $($m.ServiceDeps -join ' ')
            Write-OK "venv 创建完成（uv sync）"
        } catch {
            Write-Warn "uv 不可用，回退到 venv + pip："
            python -m venv $m.VenvDir
            & $m.Pip install -e .
            & $m.Pip install $($m.ServiceDeps -join ' ')
        }
        Pop-Location
    }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  初始化完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步："
Write-Host "  IndexTTS2 : .\services\index-tts-service\start.ps1"
Write-Host "  VoxCPM2   : .\services\voxcpm-service\start.ps1"

Pop-Location
