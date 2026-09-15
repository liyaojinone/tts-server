$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $serviceRoot)
$pythonExe = if ($env:INDEXTTS_PYTHON) { $env:INDEXTTS_PYTHON } else { Join-Path $serviceRoot ".venv\Scripts\python.exe" }
$repoDir = Join-Path $workspaceRoot "models\index-tts\repo"
$modelDir = Join-Path $workspaceRoot "models\index-tts\checkpoints"
$profileDir = Join-Path $serviceRoot "data\profiles"
$outputDir = Join-Path $workspaceRoot "models\index-tts\outputs"
$sharedProtocolSrc = Join-Path $workspaceRoot "bobogen-protocol\src"
$sharedKitSrc = Join-Path $workspaceRoot "bobogen-service-kit\src"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $repoDir)) {
    throw "IndexTTS repo not found: $repoDir"
}

if (-not (Test-Path $modelDir)) {
    throw "IndexTTS checkpoints not found: $modelDir"
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$cacheRoot = Join-Path $workspaceRoot "models\index-tts"

Set-Location $serviceRoot
$env:PYTHONPATH = "$serviceRoot;$sharedProtocolSrc;$sharedKitSrc;$repoDir"
$env:INDEXTTS_REPO_DIR = $repoDir
$env:INDEXTTS_MODEL_DIR = $modelDir
$env:INDEXTTS_PROFILE_DIR = $profileDir
$env:INDEXTTS_OUTPUT_DIR = $outputDir
# 运行期附属权重（w2v-bert/MaskGCT/campplus/bigvgan）与 wetext 缓存都放在项目内，
# 避免写入用户级 HF/ModelScope 缓存，保证整目录拷贝后仍可运行
$env:HF_HOME = Join-Path $cacheRoot "hf-home"
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:MODELSCOPE_CACHE = Join-Path $cacheRoot "modelscope-cache"
$env:MODELSCOPE_CACHE_HOME = $env:MODELSCOPE_CACHE
$env:TORCH_HOME = Join-Path $cacheRoot "torch-cache"
# 权重（含 w2v-bert/MaskGCT/campplus/bigvgan）已随目录内置，运行期不再访问 Hugging Face
$env:HF_HUB_OFFLINE = if ($env:HF_HUB_OFFLINE) { $env:HF_HUB_OFFLINE } else { "1" }
# HF xet 传输在部分网络下会卡死，默认走普通 HTTPS
$env:HF_HUB_DISABLE_XET = if ($env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET } else { "1" }
Remove-Item Env:TRANSFORMERS_CACHE -ErrorAction SilentlyContinue
$env:INDEXTTS_USE_FP16 = "true"
# CUDA kernel 需要在首次启动时用 CUDA toolkit 现场编译，容易失败且拖慢启动；
# 官方在失败时也会回退到纯 torch，这里直接关闭
$env:INDEXTTS_USE_CUDA_KERNEL = "false"
$env:INDEXTTS_USE_DEEPSPEED = "false"
$env:INDEXTTS_USE_ACCEL = "false"
$env:INDEXTTS_USE_TORCH_COMPILE = "false"
$env:INDEXTTS_PRELOAD_ON_STARTUP = if ($env:INDEXTTS_PRELOAD_ON_STARTUP) { $env:INDEXTTS_PRELOAD_ON_STARTUP } else { "false" }

Write-Host "Using Python: $pythonExe"
Write-Host "PYTHONPATH: $env:PYTHONPATH"
Write-Host "Preloading IndexTTS2 on startup: $env:INDEXTTS_PRELOAD_ON_STARTUP"
Write-Host "Starting index-tts-service on http://127.0.0.1:5104"

& $pythonExe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 5104
