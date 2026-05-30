param(
    [string]$ReferenceAudio = "E:\AiModel\tts\GPT-SoVITS-v2-240821\pangbai.wav",
    [string]$Name = "cosy-demo",
    [string]$Text = "庞白参考文本",
    [string]$Language = "zh",
    [string]$Emotion = "calm",
    [string]$Output = "cosyvoice-clone-test.wav"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ReferenceAudio)) {
    throw "Reference audio not found: $ReferenceAudio"
}

$cloneResponseJson = & curl.exe -sS `
    -X POST "http://127.0.0.1:5101/v1/clone" `
    -F "audio=@$ReferenceAudio" `
    -F "name=$Name" `
    -F "text=$Text" `
    -F "language=$Language" `
    -F "emotion=$Emotion"

if (-not $cloneResponseJson) {
    throw "Clone request returned empty response"
}

$cloneResponse = $cloneResponseJson | ConvertFrom-Json

$payload = @{
    text = "你好，这是 CosyVoice clone-test 脚本的测试。"
    voice_id = $cloneResponse.voice_id
    language = $Language
    parameters = @{}
    output = @{
        format = "wav"
    }
} | ConvertTo-Json -Depth 6

$payloadFile = Join-Path $env:TEMP "cosyvoice-clone-payload.json"
$payload | Set-Content -Path $payloadFile -Encoding UTF8
$responseHeaders = Join-Path $env:TEMP "cosyvoice-clone-headers.txt"
& curl.exe -sS `
    -D $responseHeaders `
    -H "Content-Type: application/json" `
    -o $Output `
    -X POST "http://127.0.0.1:5101/v1/synthesize" `
    --data-binary "@$payloadFile" | Out-Null

$statusLine = Get-Content $responseHeaders | Select-Object -First 1
$statusCode = ($statusLine -split " ")[1]
Remove-Item $responseHeaders -ErrorAction SilentlyContinue
Remove-Item $payloadFile -ErrorAction SilentlyContinue

[pscustomobject]@{
    clone_voice_id = $cloneResponse.voice_id
    status_code = $statusCode
    output = (Resolve-Path $Output).Path
}
