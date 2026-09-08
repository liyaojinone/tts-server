$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelId = if ($env:F5TTS_MODEL_ID) { $env:F5TTS_MODEL_ID } else { "f5_tts" }
$modelName = if ($env:F5_MODEL) { $env:F5_MODEL } else { "F5TTS_v1_Base" }
$pythonExe = if ($env:F5TTS_PYTHON) { $env:F5TTS_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = if ($env:F5TTS_REPO_DIR) { $env:F5TTS_REPO_DIR } else { Join-Path $workspaceRoot "models\f5-tts\repo" }
$profileDir = if ($env:F5TTS_PROFILE_DIR) { $env:F5TTS_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles\$modelId" }
$port = if ($env:F5TTS_PORT) { [int]$env:F5TTS_PORT } else { 5102 }
$modelStep = if ($modelName -eq "F5TTS_Base") { "1200000" } else { "1250000" }
$ckptFile = if ($env:F5_CKPT_FILE) { $env:F5_CKPT_FILE } else { Join-Path $repoDir "ckpts\$modelName\model_$modelStep.safetensors" }
$vocabFile = if ($env:F5_VOCAB_FILE) { $env:F5_VOCAB_FILE } else { Join-Path $repoDir "ckpts\$modelName\vocab.txt" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$repoSrc = Join-Path $repoDir "src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "F5-TTS repo not found: $repoDir"
}

if (-not (Test-Path $ckptFile)) {
    Write-Host "Local F5-TTS checkpoint not found for ${modelName}: $ckptFile. Official SDK will automatically download it on startup."
}

if (-not (Test-Path $vocabFile)) {
    Write-Host "Local F5-TTS vocabulary not found for ${modelName}: $vocabFile. Official SDK will automatically download it on startup."
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoSrc"
$env:F5TTS_MODEL_ID = $modelId
$env:F5_MODEL = $modelName
$env:F5_CKPT_FILE = $ckptFile
$env:F5_VOCAB_FILE = $vocabFile
$env:F5TTS_REPO_DIR = $repoDir
$env:F5TTS_PROFILE_DIR = $profileDir
$env:F5TTS_PORT = $port

Write-Host "Using Python: $pythonExe"
Write-Host "Model: $env:F5_MODEL"
Write-Host "Checkpoint: $env:F5_CKPT_FILE"
Write-Host "Vocab: $env:F5_VOCAB_FILE"
Write-Host "REPO: $env:F5TTS_REPO_DIR"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting f5tts-service on http://127.0.0.1:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port $port
