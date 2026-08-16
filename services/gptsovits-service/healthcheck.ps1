param(
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

if ($Port -eq 0) {
    $Port = if ($env:GPTSOVITS_PORT) { [int]$env:GPTSOVITS_PORT } else { 5103 }
}

$response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/health" -Method Get
$response | ConvertTo-Json -Depth 5
