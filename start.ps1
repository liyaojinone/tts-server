param(
    [switch]$Daemon,
    [int]$Port = 6006,
    [switch]$Docker,
    [string]$Model = "",
    [switch]$Status,
    [switch]$Logs,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$gatewayDir = Join-Path $root "bobogen-gateway"
$pipIndex = if ($env:PIP_INDEX) { $env:PIP_INDEX } else { "https://mirrors.aliyun.com/pypi/simple" }

function Invoke-DockerMode {
    Set-Location $root
    if ($Model) {
        switch ($Model) {
            { $_ -in @("stable-audio3", "stableaudio3", "stable_audio3") } {
                docker compose --profile stable-audio3 up -d stable-audio3
                return
            }
            default { throw "未知模型: $Model，目前 Docker v1 支持 stable-audio3" }
        }
    }
    if ($Logs) {
        docker compose logs -f gateway
        return
    }
    if ($Stop) {
        docker compose --profile stable-audio3 down
        return
    }
    if ($Status) {
        docker compose ps
        try { Invoke-RestMethod "http://127.0.0.1:$Port/v1/providers/status" | ConvertTo-Json -Depth 8 } catch {}
        return
    }
    docker compose up -d gateway
    Write-Host "Gateway: http://127.0.0.1:$Port"
    Write-Host "模型: .\start.ps1 -Docker -Model stable-audio3"
}

function Invoke-NativeMode {
    Set-Location $gatewayDir
    if ($Logs) {
        $logPaths = @(
            (Join-Path $gatewayDir "logs\gateway.out.log"),
            (Join-Path $gatewayDir "logs\gateway.err.log")
        ) | Where-Object { Test-Path $_ }
        if (-not $logPaths) {
            Write-Host "暂无 Gateway 日志"
            return
        }
        Get-Content -Path $logPaths -Wait
        return
    }
    if ($Stop) {
        foreach ($provider in @("stable_audio_3_small_sfx", "local_index_tts", "local_voxcpm", "local_gpt_sovits", "local_f5_tts", "local_cosyvoice2")) {
            try { Invoke-RestMethod -Method Post "http://127.0.0.1:$Port/v1/providers/$provider/stop" | Out-Null } catch {}
        }
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object { $_.CommandLine -like "*uvicorn app.main:create_app*" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
        return
    }
    if ($Status) {
        try { Invoke-RestMethod "http://127.0.0.1:$Port/v1/providers/status" | ConvertTo-Json -Depth 8 } catch { Write-Host "Gateway 未启动或不可达" }
        return
    }

    python -m pip install fastapi httpx pydantic pyyaml uvicorn python-multipart mcp -q -i $pipIndex
    New-Item -ItemType Directory -Force -Path (Join-Path $gatewayDir "logs") | Out-Null

    if ($Daemon) {
        $outLogPath = Join-Path $gatewayDir "logs\gateway.out.log"
        $errLogPath = Join-Path $gatewayDir "logs\gateway.err.log"
        New-Item -ItemType File -Force -Path $outLogPath, $errLogPath | Out-Null
        $args = "-m uvicorn app.main:create_app --factory --host 0.0.0.0 --port $Port"
        Start-Process python -ArgumentList $args -WorkingDirectory $gatewayDir -RedirectStandardOutput $outLogPath -RedirectStandardError $errLogPath -WindowStyle Hidden
        Write-Host "Gateway 后台启动: http://127.0.0.1:$Port"
        Write-Host "日志: $outLogPath"
        Write-Host "错误: $errLogPath"
        return
    }

    python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port $Port
}

if ($Docker) {
    Invoke-DockerMode
} else {
    Invoke-NativeMode
}
