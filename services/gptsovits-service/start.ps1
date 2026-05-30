$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = Join-Path $workspaceRoot "GPT-SoVITS-v2-240821\runtime\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

Set-Location $serviceRoot
$sharedProtocolSrc = Join-Path $workspaceRoot "local-tts-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "local-tts-service-kit\src"
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc"

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting gptsovits-service on http://127.0.0.1:5103"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5103
