[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $root "runtime\python\cp311\manifest.json"
$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
$runtimeDir = Split-Path -Parent $manifestPath
$pythonPath = Join-Path $runtimeDir $manifest.python_executable

if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
    $installedVersion = & $pythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($installedVersion -ne $manifest.python_version) {
        throw "目录内 Python 版本不匹配：期望 $($manifest.python_version)，实际 $installedVersion"
    }
    Write-Output "目录内 Python 已就绪：$pythonPath ($installedVersion)"
    exit 0
}

if (Test-Path -LiteralPath $runtimeDir) {
    throw "目录内 Python 目录不完整，拒绝覆盖：$runtimeDir"
}

$archivePath = Join-Path ([System.IO.Path]::GetTempPath()) "bobogen-cp311-$($manifest.python_version).tar.gz"

try {
    Write-Output "下载目录内 CPython $($manifest.python_version)..."
    Invoke-WebRequest -Uri $manifest.archive_url -OutFile $archivePath

    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $manifest.archive_sha256) {
        throw "CPython 归档 SHA-256 校验失败"
    }

    New-Item -ItemType Directory -Path $runtimeDir | Out-Null
    & tar.exe -xzf $archivePath --strip-components=1 -C $runtimeDir
    if ($LASTEXITCODE -ne 0) {
        throw "解压目录内 CPython 失败（tar 退出码 $LASTEXITCODE）"
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "解压后缺少 Python 入口：$pythonPath"
    }

    $installedVersion = & $pythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($installedVersion -ne $manifest.python_version) {
        throw "目录内 Python 版本不匹配：期望 $($manifest.python_version)，实际 $installedVersion"
    }
    Write-Output "目录内 Python 已安装并校验：$pythonPath ($installedVersion)"
}
finally {
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
}
