$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = if ($env:GPTSOVITS_PYTHON) { $env:GPTSOVITS_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = if ($env:GPTSOVITS_REPO_DIR) { $env:GPTSOVITS_REPO_DIR } else { Join-Path $workspaceRoot "models\gpt-sovits\repo" }
$profileDir = if ($env:GPTSOVITS_PROFILE_DIR) { $env:GPTSOVITS_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$gptPackageDir = Join-Path $repoDir "GPT_SoVITS"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "GPT-SoVITS repo not found: $repoDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoDir;$gptPackageDir"
$env:GPTSOVITS_REPO_DIR = $repoDir
$env:GPTSOVITS_PROFILE_DIR = $profileDir

Write-Host "Using Python: $pythonExe"
Write-Host "REPO: $env:GPTSOVITS_REPO_DIR"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting gptsovits-service on http://127.0.0.1:5103"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5103
