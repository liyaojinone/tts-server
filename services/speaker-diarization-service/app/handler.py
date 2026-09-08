import os
import re
from typing import Any

from bobogen_protocol.models import GenerateRequest


DEFAULT_MODEL_ID = "campplus_speaker_diarization"
DEFAULT_MODEL_NAME = "iic/speech_campplus_speaker-diarization_common"
DEFAULT_MODEL_REVISION = "master"


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


class SpeakerDiarizationHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode or _truthy(os.environ.get("SPEAKER_DIARIZATION_TEST_MODE"))
        self.model_id = os.environ.get("SPEAKER_DIARIZATION_MODEL_ID", DEFAULT_MODEL_ID)
        self.model_name = os.environ.get("SPEAKER_DIARIZATION_MODEL_NAME", DEFAULT_MODEL_NAME)
        self.model_revision = os.environ.get("SPEAKER_DIARIZATION_MODEL_REVISION", DEFAULT_MODEL_REVISION)
        self.device = os.environ.get("SPEAKER_DIARIZATION_DEVICE", "cuda:0")
        self._pipeline = None

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model": self.model_id,
            "modelName": self.model_name,
            "modelRevision": self.model_revision,
            "device": self.device,
            "ready": self.test_mode or self._pipeline is not None,
            "testMode": self.test_mode,
        }

    def warmup(self) -> dict[str, Any]:
        """Load the official ModelScope pipeline without processing audio."""
        if self.test_mode:
            return {"status": "ok", "mode": "test"}
        self._load_pipeline()
        return {
            "status": "ready",
            "model": self.model_name,
            "revision": self.model_revision,
            "device": self.device,
        }

    def diarize(self, request: GenerateRequest) -> dict[str, Any]:
        if request.model != self.model_id:
            raise ValueError(f"Unsupported model: {request.model}")
        if request.task != "audio.diarize":
            raise ValueError(f"Unsupported task: {request.task}")
        if request.output.format != "json":
            raise ValueError("Speaker diarization service currently supports json output only")

        audio = request.input.get("audio")
        if not audio:
            raise ValueError("input.audio is required")

        clip_start = float(request.input.get("clip_start", 0.0))
        min_duration = float(request.parameters.get("min_duration", 0.0) or 0.0)

        if self.test_mode:
            return {
                "model": self.model_id,
                "clip_start": clip_start,
                "segments": [
                    {
                        "index": 0,
                        "speaker": "SPEAKER_00",
                        "start": 0.0,
                        "end": 1.0,
                        "global_start": clip_start,
                        "global_end": clip_start + 1.0,
                    }
                ],
            }

        pipeline = self._load_pipeline()
        kwargs = {}
        oracle_num = request.parameters.get("oracle_num")
        if oracle_num is not None:
            kwargs["oracle_num"] = int(oracle_num)
        result = pipeline(str(audio), **kwargs)
        return {
            "model": self.model_id,
            "clip_start": clip_start,
            "segments": self._normalize_segments(result, clip_start=clip_start, min_duration=min_duration),
        }

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        self._ensure_torchaudio_sox_compat()
        try:
            from modelscope.pipelines import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "modelscope or one of its runtime dependencies is not installed. Create the speaker-diarization-service venv and install ModelScope audio dependencies."
            ) from exc

        kwargs = {
            "task": "speaker-diarization",
            "model": self.model_name,
            "device": self.device,
        }
        if self.model_revision:
            kwargs["model_revision"] = self.model_revision

        try:
            self._pipeline = pipeline(**kwargs)
        except TypeError:
            kwargs.pop("device", None)
            self._pipeline = pipeline(**kwargs)
        return self._pipeline

    @staticmethod
    def _ensure_torchaudio_sox_compat() -> None:
        """Keep ModelScope's rate-effect call working with modern torchaudio."""
        import torchaudio

        if hasattr(torchaudio, "sox_effects"):
            return

        class _SoxEffectsCompat:
            @staticmethod
            def apply_effects_tensor(waveform, sample_rate, effects):
                current_rate = int(sample_rate)
                current = waveform
                for effect in effects:
                    if not effect:
                        continue
                    if effect[0] != "rate" or len(effect) < 2:
                        raise RuntimeError(
                            "Unsupported ModelScope audio effect: "
                            f"{effect!r}"
                        )
                    target_rate = int(effect[1])
                    if target_rate != current_rate:
                        current = torchaudio.functional.resample(
                            current,
                            current_rate,
                            target_rate,
                        )
                        current_rate = target_rate
                return current, current_rate

        torchaudio.sox_effects = _SoxEffectsCompat()

    def _normalize_segments(self, result, clip_start: float, min_duration: float) -> list[dict[str, Any]]:
        raw_segments = self._extract_raw_segments(result)
        normalized = []
        for item in raw_segments:
            speaker = str(item["speaker"])
            start = float(item["start"])
            end = float(item["end"])
            if end < start:
                start, end = end, start
            if end - start < min_duration:
                continue
            normalized.append(
                {
                    "index": len(normalized),
                    "speaker": speaker,
                    "start": start,
                    "end": end,
                    "global_start": clip_start + start,
                    "global_end": clip_start + end,
                }
            )
        return normalized

    def _extract_raw_segments(self, result) -> list[dict[str, Any]]:
        if isinstance(result, dict):
            for key in ("segments", "text", "result", "output"):
                value = result.get(key)
                if value:
                    return self._extract_raw_segments(value)
            return []
        if isinstance(result, str):
            return self._segments_from_text(result)
        if isinstance(result, list):
            segments = []
            for item in result:
                if isinstance(item, dict):
                    segment = self._segment_from_dict(item)
                    if segment is not None:
                        segments.append(segment)
                elif isinstance(item, (list, tuple)):
                    segment = self._segment_from_triplet(item)
                    if segment is not None:
                        segments.append(segment)
                elif isinstance(item, str):
                    segments.extend(self._segments_from_text(item))
            return segments
        return []

    def _segment_from_dict(self, item: dict[str, Any]) -> dict[str, Any] | None:
        speaker = item.get("speaker") or item.get("speaker_id") or item.get("label")
        start = item.get("start") or item.get("start_time") or item.get("begin")
        end = item.get("end") or item.get("end_time")
        if end is None and start is not None and item.get("duration") is not None:
            end = float(start) + float(item["duration"])
        if speaker is None or start is None or end is None:
            return None
        return {"speaker": speaker, "start": start, "end": end}

    def _segment_from_triplet(self, item: list[Any] | tuple[Any, ...]) -> dict[str, Any] | None:
        if len(item) < 3:
            return None
        start, end, speaker = item[:3]
        return {"speaker": self._format_speaker(speaker), "start": start, "end": end}

    def _format_speaker(self, speaker: Any) -> str:
        if isinstance(speaker, str):
            return speaker
        return f"SPEAKER_{int(speaker):02d}"

    def _segments_from_text(self, text: str) -> list[dict[str, Any]]:
        segments = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            rttm = self._segment_from_rttm_line(line)
            if rttm is not None:
                segments.append(rttm)
        return segments

    def _segment_from_rttm_line(self, line: str) -> dict[str, Any] | None:
        parts = re.split(r"\s+", line)
        if len(parts) >= 8 and parts[0].upper() == "SPEAKER":
            start = float(parts[3])
            duration = float(parts[4])
            return {"speaker": parts[7], "start": start, "end": start + duration}
        return None
