$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = Join-Path $workspaceRoot "F5-TTS\python\py310\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$sharedProtocolSrc = Join-Path $workspaceRoot "local-tts-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "local-tts-service-kit\src"

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc"

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting f5tts-service on http://127.0.0.1:5102"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5102
