param(
    [switch]$Daemon,
    [int]$Port = 6006,
    [switch]$Docker,
    [string]$Model = "",
    [switch]$Status,
    [switch]$Logs,
    [switch]$Stop,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$gatewayDir = Join-Path $root "bobogen-gateway"
$gatewayPython = Join-Path $root "runtime\python\cp311\python.exe"
$portableLauncher = Join-Path $root "runtime\portable_python_launcher.py"
$gatewayPackages = Join-Path $root "runtime\gateway\.venv\Lib\site-packages"

function Show-Usage {
    Write-Host ""
    Write-Host "BoboGen Server - Windows 启动脚本"
    Write-Host ""
    Write-Host "用法:"
    Write-Host "  .\start.ps1 -Daemon                 后台启动 Gateway"
    Write-Host "  .\start.ps1                         前台启动 Gateway"
    Write-Host "  .\start.ps1 -Status                 查看 Provider 状态"
    Write-Host "  .\start.ps1 -Logs                   查看 Gateway 日志"
    Write-Host "  .\start.ps1 -Stop                   停止 Gateway 和本地 Provider"
    Write-Host "  .\start.ps1 -Docker -Daemon         Docker 启动 Gateway"
    Write-Host "  .\start.ps1 -Docker -Model stable-audio3"
    Write-Host "  .\start.ps1 -Docker -Status"
    Write-Host "  .\start.ps1 -Docker -Logs"
    Write-Host "  .\start.ps1 -Docker -Stop"
    Write-Host ""
    Write-Host "参数:"
    Write-Host "  -Port <number>                      Gateway 端口，默认 6006"
    Write-Host "  -Help                               显示本帮助"
    Write-Host ""
}

function Invoke-DockerMode {
    Push-Location $root
    try {
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
    } finally {
        Pop-Location
    }
}

function Invoke-NativeMode {
    Push-Location $gatewayDir
    try {
        if ($Logs) {
            $logPath = Join-Path $gatewayDir "logs\gateway.log"
            if (-not (Test-Path $logPath)) {
                Write-Host "暂无 Gateway 日志"
                return
            }
            Get-Content -Path $logPath -Wait
            return
        }
        if ($Stop) {
            foreach ($provider in @("stable_audio_3_small_sfx", "stable_audio_3_small_music", "stable_audio_3_medium", "index_tts_2", "voxcpm2", "gpt_sovits_v2pro", "f5_tts", "cosyvoice2", "tiger_dnr")) {
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

        if (-not (Test-Path $gatewayPython)) {
            throw "完整运行包的 Python 不存在：$gatewayPython。请运行 .\scripts\install-portable-python.ps1"
        }
        if (-not (Test-Path $portableLauncher)) {
            throw "完整运行包的 Python 启动器不存在：$portableLauncher"
        }
        if (-not (Test-Path $gatewayPackages)) {
            throw "Gateway 依赖目录不存在：$gatewayPackages。请使用完整运行包，或运行 .\install.ps1 -GatewayOnly 进行高级维护。"
        }
        # Gateway 进程负责下载模型权重：HF xet 传输在部分网络下会卡死，
        # 默认关闭，改用普通 HTTPS（显式设为 0 可重新开启）
        if (-not $env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET = "1" }
        New-Item -ItemType Directory -Force -Path (Join-Path $gatewayDir "logs") | Out-Null

        if ($Daemon) {
            $logPath = Join-Path $gatewayDir "logs\gateway.log"
            New-Item -ItemType File -Force -Path $logPath | Out-Null
            $daemonScript = "& '$gatewayPython' '$portableLauncher' --repo-root '$root' --packages '$gatewayPackages' --source '$gatewayDir' --module uvicorn -- app.main:create_app --factory --host 0.0.0.0 --port $Port 2>&1 | Out-File -FilePath '$logPath' -Append -Encoding utf8"
            $encodedDaemonScript = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($daemonScript))
            Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedDaemonScript) -WorkingDirectory $gatewayDir -WindowStyle Hidden
            Write-Host "Gateway 后台启动: http://127.0.0.1:$Port"
            Write-Host "日志: $logPath"
            return
        }

        & $gatewayPython $portableLauncher --repo-root $root --packages $gatewayPackages --source $gatewayDir --module uvicorn -- app.main:create_app --factory --host 0.0.0.0 --port $Port
    } finally {
        Pop-Location
    }
}

if ($Help) {
    Show-Usage
    return
}

if ($Docker) {
    Invoke-DockerMode
} else {
    Invoke-NativeMode
}
