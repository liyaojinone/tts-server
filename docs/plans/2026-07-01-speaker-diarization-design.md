# Speaker Diarization Design

## Goal

Add a local speaker diarization capability that answers "who spoke when" for uploaded audio while keeping the existing unified generate protocol unchanged.

## Scope

The first version exposes `audio.diarize` through `/v1/generate`. It returns normalized speaker time ranges such as `SPEAKER_00`, `SPEAKER_01`, start/end seconds, and optional timeline offsets. It does not perform ASR, does not assign real character names, and does not modify Qwen3-ASR or Qwen3 ForcedAligner behavior.

## Model Choice

Use ModelScope `iic/speech_campplus_speaker-diarization_common`, a CAM++ clustering pipeline. The official pipeline includes VAD, speaker embedding extraction, clustering, and speaker change handling. It is small compared with ASR models and suitable for local GPU/CPU execution. The service should prefer CUDA when available, but keep the model boundary independent from the existing Qwen service.

## Protocol

Request:

```json
{
  "model": "campplus_speaker_diarization",
  "task": "audio.diarize",
  "input": {
    "audio": {"kind": "upload", "field": "audio"},
    "clip_start": 0.0
  },
  "parameters": {
    "oracle_num": null,
    "min_duration": 0.0
  },
  "output": {"format": "json"}
}
```

Response:

```json
{
  "model": "campplus_speaker_diarization",
  "clip_start": 0.0,
  "segments": [
    {
      "index": 0,
      "speaker": "SPEAKER_00",
      "start": 0.12,
      "end": 3.84,
      "global_start": 0.12,
      "global_end": 3.84
    }
  ]
}
```

## Data Flow

The client sends audio through the existing multipart or JSON file input flow. The gateway resolves uploads to temporary local paths, validates the `audio.diarize` schema, starts the diarization provider, and forwards the same `GenerateRequest` JSON to the service. The service runs the ModelScope pipeline and normalizes either dict/list or text/RTTM-like output into stable JSON segments.

## Limitations

The first version names anonymous speakers only. Mapping `SPEAKER_00` to real roles such as "旁白" or "芳白" requires a later speaker verification/reference-voice feature. Official ModelScope notes also warn that very short effective speech under about 30 seconds and more than 10 speakers can reduce diarization quality.

