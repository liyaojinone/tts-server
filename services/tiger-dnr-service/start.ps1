$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelRoot = Join-Path $workspaceRoot "models\tiger"
$repoDir = Join-Path $workspaceRoot "models\tiger\repo"
$modelDir = Join-Path $workspaceRoot "models\tiger\TIGER-DnR"
$defaultPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonExe = if ($env:TIGER_DNR_PYTHON) { $env:TIGER_DNR_PYTHON } else { $defaultPython }
$port = if ($env:TIGER_DNR_PORT) { $env:TIGER_DNR_PORT } else { "5114" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe. Create the TIGER-DnR service environment first."
}
if (-not (Test-Path $repoDir)) {
    throw "TIGER source repository not found: $repoDir"
}

$vendoredFfmpeg = Join-Path $serviceRoot ".venv\ffmpeg\ffmpeg.exe"

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$repoDir"
if (Test-Path $vendoredFfmpeg) {
    $env:FFMPEG_BINARY = $vendoredFfmpeg
    $env:PATH = "$(Split-Path -Parent $vendoredFfmpeg);$env:PATH"
}
$env:TIGER_DNR_REPO_DIR = $repoDir
$env:TIGER_DNR_MODEL_DIR = if ($env:TIGER_DNR_MODEL_DIR) { $env:TIGER_DNR_MODEL_DIR } else { $modelDir }
$env:TIGER_DNR_JOB_ROOT = if ($env:TIGER_DNR_JOB_ROOT) { $env:TIGER_DNR_JOB_ROOT } else { Join-Path $modelRoot "runtime\jobs" }
$env:TIGER_DNR_HF_REPO_ID = if ($env:TIGER_DNR_HF_REPO_ID) { $env:TIGER_DNR_HF_REPO_ID } else { "JusperLee/TIGER-DnR" }
$env:TIGER_DNR_HF_REVISION = if ($env:TIGER_DNR_HF_REVISION) { $env:TIGER_DNR_HF_REVISION } else { "b7a59560bbca10febbcd46fb01600f868e587f57" }
$env:TIGER_DNR_DEVICE = if ($env:TIGER_DNR_DEVICE) { $env:TIGER_DNR_DEVICE } else { "cuda:0" }
$env:TIGER_DNR_PORT = $port
$env:HF_HOME = if ($env:HF_HOME) { $env:HF_HOME } else { Join-Path $modelRoot "hf-home" }
$env:HUGGINGFACE_HUB_CACHE = if ($env:HUGGINGFACE_HUB_CACHE) { $env:HUGGINGFACE_HUB_CACHE } else { Join-Path $env:HF_HOME "hub" }
$env:TORCH_HOME = if ($env:TORCH_HOME) { $env:TORCH_HOME } else { Join-Path $modelRoot "torch-cache" }
$env:NUMBA_CACHE_DIR = if ($env:NUMBA_CACHE_DIR) { $env:NUMBA_CACHE_DIR } else { Join-Path $modelRoot "numba-cache" }

Write-Host "Using Python: $pythonExe"
Write-Host "TIGER repo: $env:TIGER_DNR_REPO_DIR"
Write-Host "TIGER model cache: $env:TIGER_DNR_MODEL_DIR"
Write-Host "TIGER device: $env:TIGER_DNR_DEVICE"
Write-Host "Starting tiger-dnr-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
