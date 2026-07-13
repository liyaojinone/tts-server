$ErrorActionPreference = "Stop"

$port = if ($env:QWEN3_ASR_PORT) { $env:QWEN3_ASR_PORT } else { "5110" }
$url = "http://127.0.0.1:$port/v1/health"

$response = Invoke-RestMethod -Uri $url -TimeoutSec 5
if ($response.status -ne "ok") {
    throw "Qwen3-ASR service unhealthy: $($response | ConvertTo-Json -Compress)"
}
Write-Host ($response | ConvertTo-Json -Compress)
