$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelId = if ($env:VOXCPM_MODEL_ID) { $env:VOXCPM_MODEL_ID } else { "voxcpm2" }
$pythonExe = if ($env:VOXCPM_PYTHON) { $env:VOXCPM_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = if ($env:VOXCPM_REPO_DIR) { $env:VOXCPM_REPO_DIR } else { Join-Path $workspaceRoot "models\voxcpm\repo" }
$modelDir = if ($env:VOXCPM_MODEL_DIR) { $env:VOXCPM_MODEL_DIR } else { Join-Path $workspaceRoot "models\voxcpm\checkpoints" }
$configPath = if ($env:VOXCPM_CONFIG_PATH) { $env:VOXCPM_CONFIG_PATH } else { Join-Path $modelDir "config.json" }
$modelWeightsPath = if ($env:VOXCPM_MODEL_WEIGHTS_PATH) { $env:VOXCPM_MODEL_WEIGHTS_PATH } else { Join-Path $modelDir "model.safetensors" }
$audioVaeWeightsPath = if ($env:VOXCPM_AUDIOVAE_WEIGHTS_PATH) { $env:VOXCPM_AUDIOVAE_WEIGHTS_PATH } else { Join-Path $modelDir "audiovae.pth" }
$tokenizerPath = if ($env:VOXCPM_TOKENIZER_PATH) { $env:VOXCPM_TOKENIZER_PATH } else { Join-Path $modelDir "tokenizer.json" }
$profileDir = if ($env:VOXCPM_PROFILE_DIR) { $env:VOXCPM_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles\$modelId" }
$outputDir = if ($env:VOXCPM_OUTPUT_DIR) { $env:VOXCPM_OUTPUT_DIR } else { Join-Path $workspaceRoot "models\voxcpm\outputs\$modelId" }
$expectedArchitecture = if ($env:VOXCPM_EXPECTED_ARCHITECTURE) { $env:VOXCPM_EXPECTED_ARCHITECTURE.ToLowerInvariant() } else { "voxcpm2" }
$host = if ($env:VOXCPM_HOST) { $env:VOXCPM_HOST } else { "127.0.0.1" }
$port = if ($env:VOXCPM_PORT) { [int]$env:VOXCPM_PORT } else { 5105 }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$repoSrc = Join-Path $repoDir "src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

foreach ($required in @{
    "VoxCPM repo" = $repoDir
    "VoxCPM source" = $repoSrc
    "VoxCPM config" = $configPath
    "VoxCPM model weights" = $modelWeightsPath
    "VoxCPM AudioVAE weights" = $audioVaeWeightsPath
    "VoxCPM tokenizer" = $tokenizerPath
}.GetEnumerator()) {
    if (-not (Test-Path $required.Value)) {
        throw "$($required.Key) not found: $($required.Value)"
    }
}

try {
    $modelConfig = Get-Content -Raw -Path $configPath | ConvertFrom-Json
} catch {
    throw "VoxCPM config is not readable: $configPath. $($_.Exception.Message)"
}
if ($modelConfig.architecture -ne $expectedArchitecture) {
    throw "VoxCPM $modelId requires architecture '$expectedArchitecture', found '$($modelConfig.architecture)' in $configPath"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoSrc"
$env:VOXCPM_MODEL_ID = $modelId
$env:VOXCPM_REPO_DIR = $repoDir
$env:VOXCPM_MODEL_DIR = $modelDir
$env:VOXCPM_CONFIG_PATH = $configPath
$env:VOXCPM_MODEL_WEIGHTS_PATH = $modelWeightsPath
$env:VOXCPM_AUDIOVAE_WEIGHTS_PATH = $audioVaeWeightsPath
$env:VOXCPM_TOKENIZER_PATH = $tokenizerPath
$env:VOXCPM_PROFILE_DIR = $profileDir
$env:VOXCPM_OUTPUT_DIR = $outputDir
$env:VOXCPM_EXPECTED_ARCHITECTURE = $expectedArchitecture
$env:VOXCPM_HOST = $host
$env:VOXCPM_PORT = $port
$env:VOXCPM_PRELOAD_ON_STARTUP = if ($env:VOXCPM_PRELOAD_ON_STARTUP) { $env:VOXCPM_PRELOAD_ON_STARTUP } else { "true" }
$env:VOXCPM_LOAD_DENOISER = if ($env:VOXCPM_LOAD_DENOISER) { $env:VOXCPM_LOAD_DENOISER } else { "false" }
$env:VOXCPM_OPTIMIZE = if ($env:VOXCPM_OPTIMIZE) { $env:VOXCPM_OPTIMIZE } else { "false" }

Write-Host "Model: $env:VOXCPM_MODEL_ID"
Write-Host "REPO: $env:VOXCPM_REPO_DIR"
Write-Host "MODEL: $env:VOXCPM_MODEL_DIR"
Write-Host "Architecture: $env:VOXCPM_EXPECTED_ARCHITECTURE"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting voxcpm-service on http://${host}:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host $host --port $port
