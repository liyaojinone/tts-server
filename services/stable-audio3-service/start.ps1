$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$repoDir = Join-Path $workspaceRoot "models\stable-audio-3\repo"
$cacheRoot = Join-Path $workspaceRoot "models\stable-audio-3"
$defaultPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonExe = if ($env:STABLE_AUDIO3_PYTHON) { $env:STABLE_AUDIO3_PYTHON } else { $defaultPython }
$port = if ($env:STABLE_AUDIO3_PORT) { $env:STABLE_AUDIO3_PORT } else { "5106" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"

if (-not (Test-Path $repoDir)) {
    throw "Stable Audio 3 repo not found: $repoDir"
}

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$repoDir"
$env:STABLE_AUDIO3_REPO_DIR = $repoDir
$env:STABLE_AUDIO3_MODEL_NAME = if ($env:STABLE_AUDIO3_MODEL_NAME) { $env:STABLE_AUDIO3_MODEL_NAME } else { "small-sfx" }
$env:STABLE_AUDIO3_PORT = $port
$env:UV_CACHE_DIR = Join-Path $cacheRoot "uv-cache"
$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip-cache"
$env:HF_HOME = Join-Path $cacheRoot "hf-home"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $cacheRoot "torch-cache"
# gated 权重仓库在部分网络下 xet 传输会失败，默认关闭
$env:HF_HUB_DISABLE_XET = if ($env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET } else { "1" }

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Stable Audio 3 repo: $env:STABLE_AUDIO3_REPO_DIR"
Write-Host "HF_HOME: $env:HF_HOME"
Write-Host "Stable Audio 3 model: $env:STABLE_AUDIO3_MODEL_NAME"
Write-Host "Stable Audio 3 model id: $env:STABLE_AUDIO3_MODEL_ID"
Write-Host "Stable Audio 3 HF repo: $env:STABLE_AUDIO3_HF_REPO_ID"
Write-Host "Stable Audio 3 test mode: $env:STABLE_AUDIO3_TEST_MODE"
Write-Host "Starting stable-audio3-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
