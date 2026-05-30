$ErrorActionPreference = "Stop"

$response = Invoke-RestMethod -Uri "http://127.0.0.1:5104/v1/health" -Method Get
$response | ConvertTo-Json -Depth 5
