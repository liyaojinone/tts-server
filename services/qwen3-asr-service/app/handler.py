import os
from threading import Lock
from typing import Any

from bobogen_protocol.models import GenerateRequest


DEFAULT_MODEL_ID = "qwen3_asr_0_6b"
DEFAULT_HF_REPO_ID = "Qwen/Qwen3-ASR-0.6B"
HF_REPO_ID_BY_MODEL_ID = {
    "qwen3_asr_0_6b": "Qwen/Qwen3-ASR-0.6B",
    "qwen3_asr_1_7b": "Qwen/Qwen3-ASR-1.7B",
    "qwen3_forced_aligner_0_6b": "Qwen/Qwen3-ForcedAligner-0.6B-hf",
}


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


class _NativeForcedAligner:
    """Adapter for the Transformers-native Qwen3 ForcedAligner API."""

    def __init__(self, model: Any, processor: Any, torch_module: Any):
        self.model = model
        self.processor = processor
        self._torch = torch_module

    def align(self, *, audio: str, text: str, language: str):
        aligner_inputs, word_lists = self.processor.prepare_forced_aligner_inputs(
            audio=audio,
            transcript=text,
            language=language,
        )
        aligner_inputs = aligner_inputs.to(self.model.device, self.model.dtype)
        with self._torch.inference_mode():
            outputs = self.model(**aligner_inputs)
        return self.processor.decode_forced_alignment(
            logits=outputs.logits,
            input_ids=aligner_inputs["input_ids"],
            word_lists=word_lists,
            timestamp_token_id=self.model.config.timestamp_token_id,
        )


class Qwen3ASRHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode or _truthy(os.environ.get("QWEN3_ASR_TEST_MODE"))
        self.model_id = os.environ.get("QWEN3_ASR_MODEL_ID", DEFAULT_MODEL_ID)
        self.repo_dir = os.environ.get("QWEN3_ASR_REPO_DIR")
        self.hf_repo_id = os.environ.get("QWEN3_ASR_HF_REPO_ID") or HF_REPO_ID_BY_MODEL_ID.get(
            self.model_id,
            DEFAULT_HF_REPO_ID,
        )
        self.device = os.environ.get("QWEN3_ASR_DEVICE", "cuda:0")
        self.max_inference_batch_size = _read_int_env("QWEN3_ASR_MAX_INFERENCE_BATCH_SIZE", 1)
        self.max_new_tokens = _read_int_env("QWEN3_ASR_MAX_NEW_TOKENS", 1024)
        self.gpu_memory_utilization = float(os.environ.get("QWEN3_ASR_GPU_MEMORY_UTILIZATION", "0.85"))
        self._model = None
        self._aligner = None
        self._inference_lock = Lock()

    def warmup(self) -> None:
        if self.test_mode:
            return
        if self.model_id == "qwen3_forced_aligner_0_6b":
            self._load_aligner()
        else:
            self._load_model()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model": self.model_id,
            "hfRepoId": self.hf_repo_id,
            "device": self.device,
            "gpuRequired": True,
            "ready": self.test_mode or self._model is not None or self._aligner is not None,
            "testMode": self.test_mode,
        }

    def transcribe(self, request: GenerateRequest) -> dict[str, Any]:
        if request.model != self.model_id:
            raise ValueError(f"Unsupported model: {request.model}")
        if request.task != "asr.transcribe":
            raise ValueError(f"Unsupported task: {request.task}")
        if request.output.format != "json":
            raise ValueError("Qwen3-ASR service currently supports json output only")

        audio = request.input.get("audio")
        if not audio:
            raise ValueError("input.audio is required")

        language = request.input.get("language") or "auto"
        timestamps = bool(request.parameters.get("timestamps", False))
        batch_size = int(request.parameters.get("batch_size", 2))
        if not 1 <= batch_size <= 32:
            raise ValueError("parameters.batch_size must be between 1 and 32")
        if request.parameters.get("mode", "offline") != "offline":
            raise ValueError("Qwen3-ASR service currently supports offline mode only")

        if self.test_mode:
            if isinstance(audio, list):
                items = [
                    {
                        "index": index,
                        "text": "test transcription",
                        "language": language,
                        "duration_seconds": None,
                        "segments": [],
                        "model": self.model_id,
                    }
                    for index, _ in enumerate(audio)
                ]
                return {
                    "text": "".join(item["text"] for item in items),
                    "language": language,
                    "items": items,
                    "model": self.model_id,
                }
            return {
                "text": "test transcription",
                "language": language,
                "duration_seconds": None,
                "segments": [],
                "model": self.model_id,
            }

        model = self._load_model()
        with self._inference_lock:
            previous_batch_size = model.max_inference_batch_size
            try:
                model.max_inference_batch_size = batch_size
                result = model.transcribe(
                    audio=audio,
                    language=None if language == "auto" else language,
                    return_time_stamps=timestamps,
                )
            finally:
                model.max_inference_batch_size = previous_batch_size
        if isinstance(audio, list):
            items = [
                {
                    "index": index,
                    **self._normalize_transcription_item(item, fallback_language=language),
                }
                for index, item in enumerate(result)
            ]
            languages = [item["language"] for item in items if item["language"]]
            return {
                "text": "".join(item["text"] for item in items),
                "language": ",".join(dict.fromkeys(languages)) or language,
                "items": items,
                "model": self.model_id,
            }
        return self._normalize_transcription_result(result, fallback_language=language)

    def align(self, request: GenerateRequest) -> dict[str, Any]:
        if request.model != self.model_id:
            raise ValueError(f"Unsupported model: {request.model}")
        if request.task != "audio.align":
            raise ValueError(f"Unsupported task: {request.task}")
        if request.output.format != "json":
            raise ValueError("Qwen3 ForcedAligner service currently supports json output only")

        audio = request.input.get("audio")
        text = request.input.get("text")
        language = request.input.get("language")
        if not audio:
            raise ValueError("input.audio is required")
        if not text:
            raise ValueError("input.text is required")
        if not language:
            raise ValueError("input.language is required")

        clip_start = float(request.input.get("clip_start", 0.0))
        if self.test_mode:
            segments = [
                {
                    "index": 0,
                    "text": str(text),
                    "start": 0.0,
                    "end": 1.0,
                    "global_start": clip_start,
                    "global_end": clip_start + 1.0,
                }
            ]
            return {
                "text": str(text),
                "language": str(language),
                "clip_start": clip_start,
                "segments": segments,
                "model": self.model_id,
            }

        aligner = self._load_aligner()
        with self._inference_lock:
            result = aligner.align(
                audio=str(audio),
                text=str(text),
                language=str(language),
            )
        return self._normalize_alignment_result(
            result,
            text=str(text),
            language=str(language),
            clip_start=clip_start,
        )

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("CUDA GPU is required, but PyTorch is not installed") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is required for Qwen3-ASR; install CUDA-enabled PyTorch")
        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise RuntimeError("qwen-asr is not installed. Run the qwen3-asr-service setup first.") from exc

        self._model = Qwen3ASRModel.from_pretrained(
            self.hf_repo_id,
            dtype=torch.bfloat16,
            device_map=self.device,
            max_inference_batch_size=self.max_inference_batch_size,
            max_new_tokens=self.max_new_tokens,
        )
        return self._model

    def _load_aligner(self):
        if self._aligner is not None:
            return self._aligner
        with self._inference_lock:
            if self._aligner is not None:
                return self._aligner
            try:
                import torch
            except ImportError as exc:
                raise RuntimeError("CUDA GPU is required, but PyTorch is not installed") from exc
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA GPU is required for Qwen3 ForcedAligner; install CUDA-enabled PyTorch"
                )
            try:
                from transformers import AutoModelForTokenClassification, AutoProcessor
            except ImportError as exc:
                raise RuntimeError(
                    "Transformers with Qwen3 ForcedAligner support is not installed. "
                    "Run the qwen3-asr-service setup first."
                ) from exc

            processor = AutoProcessor.from_pretrained(self.hf_repo_id)
            model = AutoModelForTokenClassification.from_pretrained(
                self.hf_repo_id,
                dtype=torch.bfloat16,
                device_map=self.device,
            )
            self._aligner = _NativeForcedAligner(model=model, processor=processor, torch_module=torch)
        return self._aligner

    def _normalize_transcription_result(self, result, fallback_language: str) -> dict[str, Any]:
        item = result[0] if isinstance(result, list) else result
        return self._normalize_transcription_item(item, fallback_language)

    def _normalize_transcription_item(self, item, fallback_language: str) -> dict[str, Any]:
        text = self._get_value(item, "text") or ""
        language = self._get_value(item, "language") or fallback_language
        time_stamps = self._get_value(item, "time_stamps") or self._get_value(item, "timestamps") or []
        return {
            "text": text,
            "language": language,
            "duration_seconds": None,
            "segments": self._segments_from_time_stamps(time_stamps),
            "model": self.model_id,
        }

    def _get_value(self, item, key: str):
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _get_first_value(self, item, *keys: str):
        for key in keys:
            value = self._get_value(item, key)
            if value is not None:
                return value
        return None

    def _looks_like_alignment_item(self, item) -> bool:
        return self._get_first_value(
            item,
            "text",
            "word",
            "token",
            "char",
            "start_time",
            "end_time",
            "start",
            "end",
        ) is not None

    def _alignment_items(self, result) -> list[Any]:
        if result is None:
            return []
        if isinstance(result, dict):
            for key in ("segments", "items", "words", "tokens", "time_stamps", "timestamps"):
                nested = result.get(key)
                if nested is not None:
                    return self._alignment_items(nested)
            return [result]
        if isinstance(result, (str, bytes)):
            return []
        if isinstance(result, (list, tuple)):
            items: list[Any] = []
            for item in result:
                if self._looks_like_alignment_item(item):
                    items.append(item)
                else:
                    items.extend(self._alignment_items(item))
            return items
        if self._looks_like_alignment_item(result):
            return [result]
        if hasattr(result, "__iter__"):
            return self._alignment_items(list(result))
        return []

    def _segments_from_time_stamps(self, time_stamps) -> list[dict[str, Any]]:
        segments = []
        for index, stamp in enumerate(time_stamps or []):
            if isinstance(stamp, dict):
                segments.append(stamp)
                continue
            if isinstance(stamp, (list, tuple)) and len(stamp) >= 2:
                segments.append({"index": index, "start": stamp[0], "end": stamp[1]})
        return segments

    def _normalize_alignment_result(
        self,
        result,
        text: str,
        language: str,
        clip_start: float,
    ) -> dict[str, Any]:
        segments = []
        for index, item in enumerate(self._alignment_items(result)):
            segment_text = self._get_first_value(item, "text", "word", "token", "char") or ""
            start = float(
                self._get_first_value(item, "start_time", "start", "start_seconds", "startSeconds")
                or 0.0
            )
            end = float(
                self._get_first_value(item, "end_time", "end", "end_seconds", "endSeconds") or start
            )
            if not segment_text and end <= start:
                continue
            segments.append(
                {
                    "index": index,
                    "text": segment_text,
                    "start": start,
                    "end": end,
                    "global_start": clip_start + start,
                    "global_end": clip_start + end,
                }
            )
        return {
            "text": text,
            "language": language,
            "clip_start": clip_start,
            "segments": segments,
            "model": self.model_id,
        }
