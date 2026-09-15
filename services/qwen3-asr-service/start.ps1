$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$cacheRoot = Join-Path $workspaceRoot "models\qwen3-asr"
$repoDir = Join-Path $cacheRoot "repo"
$defaultPython = Join-Path $workspaceRoot "runtime\python\cp311\python.exe"
$portableLauncher = Join-Path $workspaceRoot "runtime\portable_python_launcher.py"
$defaultPackages = Join-Path $serviceRoot ".venv\Lib\site-packages"
$servicePackages = if ($env:QWEN3_ASR_PACKAGES) { $env:QWEN3_ASR_PACKAGES } else { $defaultPackages }
$usePortableRuntime = -not [bool]$env:QWEN3_ASR_PYTHON
$pythonExe = if ($env:QWEN3_ASR_PYTHON) { $env:QWEN3_ASR_PYTHON } else { $defaultPython }
$port = if ($env:QWEN3_ASR_PORT) { $env:QWEN3_ASR_PORT } else { "5110" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe. Create the provider-specific service environment first."
}
if ($usePortableRuntime -and (-not (Test-Path $portableLauncher))) { throw "Portable Python launcher not found: $portableLauncher" }
if ($usePortableRuntime -and (-not (Test-Path $servicePackages))) { throw "Service packages not found: $servicePackages" }

Set-Location $repoDir
# 权重缓存显式指向 BoboGenServer 内的受管目录，避免受用户 HF_* / TRANSFORMERS_CACHE 影响
$hfHome = Join-Path $cacheRoot "hf-home"
$env:HF_HOME = $hfHome
$env:HF_HUB_CACHE = Join-Path $hfHome "hub"
Remove-Item Env:TRANSFORMERS_CACHE -ErrorAction SilentlyContinue
Remove-Item Env:HUGGINGFACE_HUB_CACHE -ErrorAction SilentlyContinue

$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$repoDir"
$env:QWEN3_ASR_REPO_DIR = $repoDir
$env:QWEN3_ASR_MODEL_ID = if ($env:QWEN3_ASR_MODEL_ID) { $env:QWEN3_ASR_MODEL_ID } else { "qwen3_asr_0_6b" }
$env:QWEN3_ASR_HF_REPO_ID = if ($env:QWEN3_ASR_HF_REPO_ID) { $env:QWEN3_ASR_HF_REPO_ID } else { "Qwen/Qwen3-ASR-0.6B" }
$env:QWEN3_ASR_DEVICE = if ($env:QWEN3_ASR_DEVICE) { $env:QWEN3_ASR_DEVICE } else { "cuda:0" }
$env:QWEN3_ASR_PORT = $port
if ($env:QWEN3_ASR_HF_ENDPOINT) {
    $env:HF_ENDPOINT = $env:QWEN3_ASR_HF_ENDPOINT
}

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Qwen3-ASR repo: $env:QWEN3_ASR_REPO_DIR"
Write-Host "Qwen3-ASR model id: $env:QWEN3_ASR_MODEL_ID"
Write-Host "Qwen3-ASR HF repo: $env:QWEN3_ASR_HF_REPO_ID"
Write-Host "Hugging Face endpoint: $env:HF_ENDPOINT"
Write-Host "Hugging Face cache: $env:HF_HUB_CACHE"
Write-Host "Qwen3-ASR device: $env:QWEN3_ASR_DEVICE"
Write-Host "Qwen3-ASR test mode: $env:QWEN3_ASR_TEST_MODE"
Write-Host "Starting qwen3-asr-service on http://127.0.0.1:$port"

if ($usePortableRuntime) {
    & $pythonExe $portableLauncher --repo-root $workspaceRoot --packages $servicePackages --module uvicorn -- app.main:create_app --factory --host 127.0.0.1 --port $port
} else {
    & $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
}
