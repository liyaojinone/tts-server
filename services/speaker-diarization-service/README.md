# Speaker Diarization Service

Local speaker diarization service for ModelScope CAM++.

## Model

| Model ID | ModelScope model | Task | Port |
|----------|------------------|------|------|
| `campplus_speaker_diarization` | `iic/speech_campplus_speaker-diarization_common` | `audio.diarize` | `5113` |

This service answers "who spoke when". It returns anonymous labels such as `SPEAKER_00` and `SPEAKER_01`; it does not transcribe speech and does not map speakers to real character names.

## Setup

Create a dedicated environment and install CUDA PyTorch plus ModelScope audio dependencies.

```powershell
cd services/speaker-diarization-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -e ..\..\bobogen-protocol
.\.venv\Scripts\python.exe -m pip install -e .
```

The ModelScope cache is placed under `models/speaker-diarization` by `start.ps1`. The default ModelScope revision is `master`; older examples may mention `v1.0.0`, but the current model repository does not expose that revision.

## Run

```powershell
.\start.ps1
```

The default service URL is `http://127.0.0.1:5113`.

## API

```bash
curl -sS -X POST http://127.0.0.1:5113/v1/diarize \
  -H "Content-Type: application/json" \
  -d '{
    "model": "campplus_speaker_diarization",
    "task": "audio.diarize",
    "input": {
      "audio": "E:/audio/dialogue.wav",
      "clip_start": 10.0
    },
    "parameters": {
      "oracle_num": 2,
      "min_duration": 0.0
    },
    "output": {"format": "json"}
  }'
```

Response:

```json
{
  "model": "campplus_speaker_diarization",
  "clip_start": 10.0,
  "segments": [
    {
      "index": 0,
      "speaker": "SPEAKER_00",
      "start": 0.12,
      "end": 3.84,
      "global_start": 10.12,
      "global_end": 13.84
    }
  ]
}
```

## Notes

`oracle_num` can improve results when the speaker count is known. Very short effective speech and more than 10 speakers can reduce quality. For real role names, add a later speaker verification flow with reference voices.
