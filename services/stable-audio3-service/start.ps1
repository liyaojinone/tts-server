$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$repoDir = Join-Path $workspaceRoot "models\stable-audio-3\repo"
$defaultPython = Join-Path $repoDir ".venv\Scripts\python.exe"
$pythonExe = if ($env:STABLE_AUDIO3_PYTHON) { $env:STABLE_AUDIO3_PYTHON } else { $defaultPython }
$sharedProtocolSrc = Join-Path $workspaceRoot "local-tts-protocol\src"

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

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Stable Audio 3 repo: $env:STABLE_AUDIO3_REPO_DIR"
Write-Host "Stable Audio 3 model: $env:STABLE_AUDIO3_MODEL_NAME"
Write-Host "Starting stable-audio3-service on http://127.0.0.1:5106"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5106
