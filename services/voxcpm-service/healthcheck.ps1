param(
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

if ($Port -eq 0) {
    $Port = if ($env:VOXCPM_PORT) { [int]$env:VOXCPM_PORT } else { 5105 }
}

$response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/health" -Method Get
$response | ConvertTo-Json -Depth 5
