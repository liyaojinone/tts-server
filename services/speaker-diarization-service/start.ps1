$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$cacheRoot = Join-Path $workspaceRoot "models\speaker-diarization"
$defaultPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonExe = if ($env:SPEAKER_DIARIZATION_PYTHON) { $env:SPEAKER_DIARIZATION_PYTHON } else { $defaultPython }
$port = if ($env:SPEAKER_DIARIZATION_PORT) { $env:SPEAKER_DIARIZATION_PORT } else { "5113" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe. Create the service venv and install ModelScope audio dependencies first."
}

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc"
$env:SPEAKER_DIARIZATION_MODEL_ID = if ($env:SPEAKER_DIARIZATION_MODEL_ID) { $env:SPEAKER_DIARIZATION_MODEL_ID } else { "campplus_speaker_diarization" }
$env:SPEAKER_DIARIZATION_MODEL_NAME = if ($env:SPEAKER_DIARIZATION_MODEL_NAME) { $env:SPEAKER_DIARIZATION_MODEL_NAME } else { "iic/speech_campplus_speaker-diarization_common" }
$env:SPEAKER_DIARIZATION_MODEL_REVISION = if ($env:SPEAKER_DIARIZATION_MODEL_REVISION) { $env:SPEAKER_DIARIZATION_MODEL_REVISION } else { "master" }
$env:SPEAKER_DIARIZATION_DEVICE = if ($env:SPEAKER_DIARIZATION_DEVICE) { $env:SPEAKER_DIARIZATION_DEVICE } else { "cuda:0" }
$env:SPEAKER_DIARIZATION_PORT = $port
$env:MODELSCOPE_CACHE = Join-Path $cacheRoot "modelscope-cache"
$env:MODELSCOPE_CACHE_HOME = $env:MODELSCOPE_CACHE
$env:TORCH_HOME = Join-Path $cacheRoot "torch-cache"
$env:PIP_CACHE_DIR = Join-Path $cacheRoot "pip-cache"

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "ModelScope cache: $env:MODELSCOPE_CACHE"
Write-Host "Speaker diarization model id: $env:SPEAKER_DIARIZATION_MODEL_ID"
Write-Host "Speaker diarization model name: $env:SPEAKER_DIARIZATION_MODEL_NAME"
Write-Host "Speaker diarization model revision: $env:SPEAKER_DIARIZATION_MODEL_REVISION"
Write-Host "Speaker diarization device: $env:SPEAKER_DIARIZATION_DEVICE"
Write-Host "Speaker diarization test mode: $env:SPEAKER_DIARIZATION_TEST_MODE"
Write-Host "Starting speaker-diarization-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
