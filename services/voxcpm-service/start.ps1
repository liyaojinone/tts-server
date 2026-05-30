$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$repoDir = Join-Path $workspaceRoot "models\voxcpm\repo"
$modelDir = Join-Path $workspaceRoot "models\voxcpm\checkpoints"
$profileDir = Join-Path $serviceRoot "data\profiles"
$outputDir = Join-Path $workspaceRoot "models\voxcpm\outputs"
$sharedProtocolSrc = Join-Path $workspaceRoot "local-tts-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "local-tts-service-kit\src"
$repoSrc = Join-Path $repoDir "src"

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoSrc"
$env:VOXCPM_REPO_DIR = $repoDir
$env:VOXCPM_MODEL_DIR = $modelDir
$env:VOXCPM_PROFILE_DIR = $profileDir
$env:VOXCPM_OUTPUT_DIR = $outputDir
$env:VOXCPM_PRELOAD_ON_STARTUP = "true"
$env:VOXCPM_LOAD_DENOISER = "false"
$env:VOXCPM_OPTIMIZE = "false"

Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting voxcpm-service on http://127.0.0.1:5105"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5105
