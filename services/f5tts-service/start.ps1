$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelId = if ($env:F5TTS_MODEL_ID) { $env:F5TTS_MODEL_ID } else { "f5_tts" }
$pythonExe = if ($env:F5TTS_PYTHON) { $env:F5TTS_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = if ($env:F5TTS_REPO_DIR) { $env:F5TTS_REPO_DIR } else { Join-Path $workspaceRoot "models\f5-tts\repo" }
$profileDir = if ($env:F5TTS_PROFILE_DIR) { $env:F5TTS_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles\$modelId" }
$port = if ($env:F5TTS_PORT) { [int]$env:F5TTS_PORT } else { 5102 }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$repoSrc = Join-Path $repoDir "src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "F5-TTS repo not found: $repoDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoSrc"
$env:F5TTS_MODEL_ID = $modelId
$env:F5TTS_REPO_DIR = $repoDir
$env:F5TTS_PROFILE_DIR = $profileDir
$env:F5TTS_PORT = $port

Write-Host "Using Python: $pythonExe"
Write-Host "Model: $env:F5TTS_MODEL_ID"
Write-Host "REPO: $env:F5TTS_REPO_DIR"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting f5tts-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
