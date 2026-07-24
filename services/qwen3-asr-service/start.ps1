$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$cacheRoot = Join-Path $workspaceRoot "models\qwen3-asr"
$repoDir = Join-Path $cacheRoot "repo"
$defaultPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonExe = if ($env:QWEN3_ASR_PYTHON) { $env:QWEN3_ASR_PYTHON } else { $defaultPython }
$port = if ($env:QWEN3_ASR_PORT) { $env:QWEN3_ASR_PORT } else { "5110" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe. Create the provider-specific service environment first."
}

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$repoDir"
$env:QWEN3_ASR_REPO_DIR = $repoDir
$env:QWEN3_ASR_MODEL_ID = if ($env:QWEN3_ASR_MODEL_ID) { $env:QWEN3_ASR_MODEL_ID } else { "qwen3_asr_0_6b" }
$env:QWEN3_ASR_HF_REPO_ID = if ($env:QWEN3_ASR_HF_REPO_ID) { $env:QWEN3_ASR_HF_REPO_ID } else { "Qwen/Qwen3-ASR-0.6B" }
$env:QWEN3_ASR_MODEL_DIR = if ($env:QWEN3_ASR_MODEL_DIR) { $env:QWEN3_ASR_MODEL_DIR } else { Join-Path $cacheRoot "Qwen3-ASR-0.6B" }
$env:QWEN3_ASR_DEVICE = if ($env:QWEN3_ASR_DEVICE) { $env:QWEN3_ASR_DEVICE } else { "cuda:0" }
$env:QWEN3_ASR_PORT = $port
$env:UV_CACHE_DIR = Join-Path $cacheRoot "uv-cache"
$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip-cache"
$env:HF_HOME = Join-Path $cacheRoot "hf-home"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $cacheRoot "torch-cache"

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Qwen3-ASR repo: $env:QWEN3_ASR_REPO_DIR"
Write-Host "HF_HOME: $env:HF_HOME"
Write-Host "Qwen3-ASR model id: $env:QWEN3_ASR_MODEL_ID"
Write-Host "Qwen3-ASR HF repo: $env:QWEN3_ASR_HF_REPO_ID"
Write-Host "Qwen3-ASR model dir: $env:QWEN3_ASR_MODEL_DIR"
Write-Host "Qwen3-ASR device: $env:QWEN3_ASR_DEVICE"
Write-Host "Qwen3-ASR test mode: $env:QWEN3_ASR_TEST_MODE"
Write-Host "Starting qwen3-asr-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
