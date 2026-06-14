$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = Join-Path $workspaceRoot "models\index-tts\repo\.venv\Scripts\python.exe"
$repoDir = Join-Path $workspaceRoot "models\index-tts\repo"
$modelDir = Join-Path $workspaceRoot "models\index-tts\checkpoints"
$profileDir = Join-Path $serviceRoot "data\profiles"
$outputDir = Join-Path $workspaceRoot "models\index-tts\outputs"
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "IndexTTS repo not found: $repoDir"
}

if (-not (Test-Path $modelDir)) {
    throw "IndexTTS checkpoints not found: $modelDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoDir"
$env:INDEXTTS_REPO_DIR = $repoDir
$env:INDEXTTS_MODEL_DIR = $modelDir
$env:INDEXTTS_PROFILE_DIR = $profileDir
$env:INDEXTTS_OUTPUT_DIR = $outputDir
$env:INDEXTTS_USE_FP16 = "true"
$env:INDEXTTS_USE_CUDA_KERNEL = "true"
$env:INDEXTTS_USE_DEEPSPEED = "false"
$env:INDEXTTS_USE_ACCEL = "false"
$env:INDEXTTS_USE_TORCH_COMPILE = "false"
$env:INDEXTTS_PRELOAD_ON_STARTUP = "true"

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Preloading IndexTTS2 on startup: $env:INDEXTTS_PRELOAD_ON_STARTUP"
Write-Host "Starting index-tts-service on http://127.0.0.1:5104"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5104
