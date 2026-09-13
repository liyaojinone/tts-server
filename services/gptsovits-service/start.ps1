$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$modelId = if ($env:GPTSOVITS_MODEL_ID) { $env:GPTSOVITS_MODEL_ID } else { "gpt_sovits_v2pro" }
$pythonExe = if ($env:GPTSOVITS_PYTHON) { $env:GPTSOVITS_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = if ($env:GPTSOVITS_REPO_DIR) { $env:GPTSOVITS_REPO_DIR } else { Join-Path $workspaceRoot "models\gpt-sovits\repo" }
$modelDir = if ($env:GPTSOVITS_MODEL_DIR) { $env:GPTSOVITS_MODEL_DIR } else { Join-Path $workspaceRoot "models\gpt-sovits\checkpoints\$modelId" }
$gptWeightsPath = if ($env:GPTSOVITS_GPT_WEIGHTS_PATH) { $env:GPTSOVITS_GPT_WEIGHTS_PATH } else { Join-Path $modelDir "s1v3.ckpt" }
$sovitsWeightsPath = if ($env:GPTSOVITS_SOVITS_WEIGHTS_PATH) { $env:GPTSOVITS_SOVITS_WEIGHTS_PATH } else { Join-Path $modelDir "v2Pro\s2Gv2Pro.pth" }
$bertBasePath = if ($env:GPTSOVITS_BERT_BASE_PATH) { $env:GPTSOVITS_BERT_BASE_PATH } else { Join-Path $modelDir "chinese-roberta-wwm-ext-large" }
$cnhuhbertBasePath = if ($env:GPTSOVITS_CNHUBERT_BASE_PATH) { $env:GPTSOVITS_CNHUBERT_BASE_PATH } else { Join-Path $modelDir "chinese-hubert-base" }
$svWeightsPath = if ($env:GPTSOVITS_SV_WEIGHTS_PATH) { $env:GPTSOVITS_SV_WEIGHTS_PATH } else { Join-Path $modelDir "sv\pretrained_eres2netv2w24s4ep4.ckpt" }
$profileDir = if ($env:GPTSOVITS_PROFILE_DIR) { $env:GPTSOVITS_PROFILE_DIR } else { Join-Path $serviceRoot "data\profiles\$modelId" }
$outputDir = if ($env:GPTSOVITS_OUTPUT_DIR) { $env:GPTSOVITS_OUTPUT_DIR } else { Join-Path $workspaceRoot "models\gpt-sovits\outputs\$modelId" }
$runtimeConfigPath = if ($env:GPTSOVITS_RUNTIME_CONFIG_PATH) { $env:GPTSOVITS_RUNTIME_CONFIG_PATH } else { Join-Path $serviceRoot "data\runtime\$modelId\tts_infer.yaml" }
$bindHost = if ($env:GPTSOVITS_HOST) { $env:GPTSOVITS_HOST } else { "127.0.0.1" }
$port = if ($env:GPTSOVITS_PORT) { [int]$env:GPTSOVITS_PORT } else { 5103 }
$upstreamVersion = if ($env:GPTSOVITS_UPSTREAM_VERSION) { $env:GPTSOVITS_UPSTREAM_VERSION } else { "v2Pro" }
$device = if ($env:GPTSOVITS_DEVICE) { $env:GPTSOVITS_DEVICE } else { "cuda" }
$isHalf = if ($env:GPTSOVITS_IS_HALF) { $env:GPTSOVITS_IS_HALF } else { "true" }
$preloadOnStartup = if ($env:GPTSOVITS_PRELOAD_ON_STARTUP) { $env:GPTSOVITS_PRELOAD_ON_STARTUP } else { "false" }
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"
$gptPackageDir = Join-Path $repoDir "GPT_SoVITS"
$torchcodecFfmpegDir = Join-Path (Split-Path -Parent (Split-Path -Parent $pythonExe)) "ffmpeg"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "GPT-SoVITS repo not found: $repoDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runtimeConfigPath) | Out-Null

Set-Location $repoDir
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoDir;$gptPackageDir"
if (Test-Path $torchcodecFfmpegDir) {
    $env:PATH = "$torchcodecFfmpegDir;$env:PATH"
}
$env:GPTSOVITS_MODEL_ID = $modelId
$env:GPTSOVITS_UPSTREAM_VERSION = $upstreamVersion
$env:GPTSOVITS_REPO_DIR = $repoDir
$env:GPTSOVITS_MODEL_DIR = $modelDir
$env:GPTSOVITS_GPT_WEIGHTS_PATH = $gptWeightsPath
$env:GPTSOVITS_SOVITS_WEIGHTS_PATH = $sovitsWeightsPath
$env:GPTSOVITS_BERT_BASE_PATH = $bertBasePath
$env:bert_path = $bertBasePath
$env:GPTSOVITS_CNHUBERT_BASE_PATH = $cnhuhbertBasePath
$env:GPTSOVITS_SV_WEIGHTS_PATH = $svWeightsPath
$env:GPTSOVITS_PROFILE_DIR = $profileDir
$env:GPTSOVITS_OUTPUT_DIR = $outputDir
$env:GPTSOVITS_RUNTIME_CONFIG_PATH = $runtimeConfigPath
$env:GPTSOVITS_HOST = $bindHost
$env:GPTSOVITS_PORT = $port
$env:GPTSOVITS_DEVICE = $device
$env:GPTSOVITS_IS_HALF = $isHalf
$env:GPTSOVITS_PRELOAD_ON_STARTUP = $preloadOnStartup

Write-Host "Using Python: $pythonExe"
Write-Host "Model: $env:GPTSOVITS_MODEL_ID ($env:GPTSOVITS_UPSTREAM_VERSION)"
Write-Host "REPO: $env:GPTSOVITS_REPO_DIR"
Write-Host "GPT weights: $env:GPTSOVITS_GPT_WEIGHTS_PATH"
Write-Host "SoVITS weights: $env:GPTSOVITS_SOVITS_WEIGHTS_PATH"
Write-Host "Speaker encoder: $env:GPTSOVITS_SV_WEIGHTS_PATH"
Write-Host "Preloading: $env:GPTSOVITS_PRELOAD_ON_STARTUP"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Starting gptsovits-service on http://${bindHost}:$port"

& $pythonExe -m uvicorn app.main:create_app --factory --host $bindHost --port $port
