$port = if ($env:SPEAKER_DIARIZATION_PORT) { $env:SPEAKER_DIARIZATION_PORT } else { "5113" }
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/v1/health"
if ($response.StatusCode -ne 200) {
    throw "speaker-diarization-service healthcheck failed: $($response.StatusCode)"
}
Write-Host $response.Content
