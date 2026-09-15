$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelId = if ($env:COSYVOICE_MODEL_ID) { $env:COSYVOICE_MODEL_ID } else { "cosyvoice2" }
$defaultPython = Join-Path $workspaceRoot "runtime\python\cp311\python.exe"
$portableLauncher = Join-Path $workspaceRoot "runtime\portable_python_launcher.py"
$servicePackages = Join-Path $serviceRoot ".venv\Lib\site-packages"
$usePortableRuntime = -not [bool]$env:COSYVOICE_PYTHON
$pythonExe = if ($env:COSYVOICE_PYTHON) { $env:COSYVOICE_PYTHON } else { $defaultPython }
$repoDir = if ($env:COSYVOICE_REPO_DIR) { $env:COSYVOICE_REPO_DIR } else { Join-Path $workspaceRoot "models\cosyvoice\repo" }
$profileDir = if ($env:COSYVOICE_PROFILE_DIR) { $env:COSYVOICE_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles\$modelId" }
$port = if ($env:COSYVOICE_PORT) { [int]$env:COSYVOICE_PORT } else { 5101 }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$thirdPartyDir = Join-Path $repoDir "third_party\Matcha-TTS"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}
if ($usePortableRuntime -and (-not (Test-Path $portableLauncher))) { throw "Portable Python launcher not found: $portableLauncher" }
if ($usePortableRuntime -and (-not (Test-Path $servicePackages))) { throw "Service packages not found: $servicePackages" }

if (-not (Test-Path $repoDir)) {
    throw "CosyVoice repo not found: $repoDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoDir;$thirdPartyDir"
$env:COSYVOICE_MODEL_ID = $modelId
$env:COSYVOICE_REPO_DIR = $repoDir
$env:COSYVOICE_PROFILE_DIR = $profileDir
$env:COSYVOICE_PORT = $port

Write-Host "Using Python: $pythonExe"
Write-Host "Model: $env:COSYVOICE_MODEL_ID"
Write-Host "REPO: $env:COSYVOICE_REPO_DIR"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting cosyvoice-service on http://127.0.0.1:$port"

if ($usePortableRuntime) {
    & $pythonExe $portableLauncher --repo-root $workspaceRoot --packages $servicePackages --module uvicorn -- app.main:create_app --factory --host 127.0.0.1 --port $port
} else {
    & $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
}
