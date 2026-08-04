from __future__ import annotations

import hashlib
from itertools import chain
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable
import uuid

import numpy as np
import soundfile as sf


ProgressCallback = Callable[[float], None]
CancelCallback = Callable[[], bool]
PipelineProgressCallback = Callable[[str, float, str], None]


class SeparationCancelled(RuntimeError):
    pass


def _resample_audio(
    audio: np.ndarray,
    source_rate: int,
    target_rate: int,
    *,
    target_frames: int | None = None,
) -> np.ndarray:
    if source_rate == target_rate:
        result = audio
    else:
        try:
            from scipy.signal import resample_poly

            divisor = math.gcd(source_rate, target_rate)
            result = resample_poly(
                audio,
                target_rate // divisor,
                source_rate // divisor,
                axis=0,
            )
        except ImportError:
            source_positions = np.arange(audio.shape[0], dtype=np.float64)
            output_frames = max(
                1,
                round(audio.shape[0] * target_rate / source_rate),
            )
            target_positions = np.linspace(
                0,
                max(audio.shape[0] - 1, 0),
                output_frames,
            )
            result = np.stack(
                [
                    np.interp(
                        target_positions,
                        source_positions,
                        audio[:, channel],
                    )
                    for channel in range(audio.shape[1])
                ],
                axis=1,
            )

    result = np.asarray(result, dtype=np.float32)
    if target_frames is None:
        return result
    if result.shape[0] < target_frames:
        result = np.pad(
            result,
            ((0, target_frames - result.shape[0]), (0, 0)),
        )
    return result[:target_frames]


def residual_background(
    source: np.ndarray,
    dialogue: np.ndarray,
) -> np.ndarray:
    if source.shape != dialogue.shape:
        raise ValueError(
            "dialogue must match decoded source shape before subtraction"
        )
    background = source.astype(np.float32, copy=False) - dialogue.astype(
        np.float32,
        copy=False,
    )
    if not np.isfinite(background).all():
        raise RuntimeError("background contains non-finite samples")
    return background


def decode_audio(path: Path) -> tuple[np.ndarray, int]:
    try:
        audio, sample_rate = sf.read(
            path,
            dtype="float32",
            always_2d=True,
        )
        return np.ascontiguousarray(audio), int(sample_rate)
    except (OSError, RuntimeError):
        ffmpeg = shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg"))
        if ffmpeg is None:
            raise RuntimeError(
                f"Unable to decode {path}; ffmpeg was not found"
            )
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as temporary:
            decoded_path = Path(temporary.name)
        try:
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(path),
                    "-map",
                    "0:a:0",
                    "-c:a",
                    "pcm_f32le",
                    str(decoded_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip()
                    or f"ffmpeg failed to decode {path}"
                )
            audio, sample_rate = sf.read(
                decoded_path,
                dtype="float32",
                always_2d=True,
            )
            return np.ascontiguousarray(audio), int(sample_rate)
        finally:
            decoded_path.unlink(missing_ok=True)


def _sha256(
    path: Path,
    should_cancel: CancelCallback | None = None,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            if should_cancel is not None and should_cancel():
                raise SeparationCancelled("separation cancelled")
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_stream_source(
    source_path: Path,
    *,
    work_dir: Path,
    should_cancel: CancelCallback,
) -> tuple[Path, object, bool]:
    try:
        info = sf.info(source_path)
        if info.frames <= 0 or info.channels <= 0:
            raise RuntimeError("decoded source contains no audio frames")
        return source_path, info, False
    except (OSError, RuntimeError):
        ffmpeg = shutil.which(
            os.environ.get("FFMPEG_BINARY", "ffmpeg")
        )
        if ffmpeg is None:
            raise RuntimeError(
                f"Unable to decode {source_path}; ffmpeg was not found"
            )

    work_dir.mkdir(parents=True, exist_ok=True)
    decoded_path = work_dir / "source.decoded.wav"
    partial_path = work_dir / "source.decoded.partial.wav"
    decoded_path.unlink(missing_ok=True)
    partial_path.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryFile() as error_output:
            process = subprocess.Popen(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source_path),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-sn",
                    "-dn",
                    "-c:a",
                    "pcm_f32le",
                    "-f",
                    "wav",
                    str(partial_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=error_output,
            )
            while process.poll() is None:
                if should_cancel():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise SeparationCancelled(
                        "separation cancelled"
                    )
                time.sleep(0.05)
            if process.returncode != 0:
                error_output.seek(0)
                stderr = error_output.read(
                    64 * 1024
                ).decode(
                    "utf-8",
                    errors="replace",
                )
                raise RuntimeError(
                    stderr.strip()
                    or f"ffmpeg failed to decode {source_path}"
                )
        info = sf.info(partial_path)
        if info.frames <= 0 or info.channels <= 0:
            raise RuntimeError("decoded source contains no audio frames")
        os.replace(partial_path, decoded_path)
        return decoded_path, sf.info(decoded_path), True
    except Exception:
        decoded_path.unlink(missing_ok=True)
        partial_path.unlink(missing_ok=True)
        raise


def _streaming_artifact_metadata(
    *,
    partials: dict[str, Path],
    finals: dict[str, Path],
    sample_rate: int,
    channels: int,
    frame_count: int,
    should_cancel: CancelCallback,
) -> list[dict]:
    artifacts = []
    for role in ("dialogue", "background"):
        path = partials[role]
        final_path = finals[role]
        artifacts.append(
            {
                "id": uuid.uuid4().hex,
                "role": role,
                "filename": final_path.name,
                "content_type": "audio/wav",
                "size_bytes": path.stat().st_size,
                "sample_rate": sample_rate,
                "channels": channels,
                "frame_count": frame_count,
                "sha256": _sha256(
                    path,
                    should_cancel=should_cancel,
                ),
                "_path": str(final_path),
            }
        )
    return artifacts


def _create_fresh_zero_memmap(
    path: Path,
    *,
    shape: tuple[int, ...],
    should_cancel: CancelCallback,
) -> np.memmap:
    if should_cancel():
        raise SeparationCancelled("separation cancelled")

    mapped = None
    try:
        byte_count = (
            math.prod(shape)
            * np.dtype(np.float32).itemsize
        )
        with path.open("x+b") as backing_file:
            backing_file.truncate(byte_count)
        if should_cancel():
            raise SeparationCancelled(
                "separation cancelled"
            )

        # A freshly extended file reads as zero on supported platforms.
        # Mapping it directly avoids touching every duration-sized page.
        mapped = np.memmap(
            path,
            dtype=np.float32,
            mode="r+",
            shape=shape,
        )
        if should_cancel():
            raise SeparationCancelled(
                "separation cancelled"
            )
        return mapped
    except Exception:
        if mapped is not None:
            mapped._mmap.close()
        path.unlink(missing_ok=True)
        raise


def _publish_streaming_artifacts(
    *,
    output_dir: Path,
    source_path: Path,
    accumulated: np.memmap,
    weights: np.memmap,
    sample_rate: int,
    channels: int,
    frame_count: int,
    io_block_frames: int,
    progress: PipelineProgressCallback,
    should_cancel: CancelCallback,
) -> list[dict]:
    partials = {
        "dialogue": output_dir / "dialogue.partial.wav",
        "background": output_dir / "background.partial.wav",
    }
    finals = {
        "dialogue": output_dir / "dialogue.wav",
        "background": output_dir / "background.wav",
    }
    for path in [*partials.values(), *finals.values()]:
        path.unlink(missing_ok=True)

    try:
        with (
            sf.SoundFile(source_path, mode="r") as source_file,
            sf.SoundFile(
                partials["dialogue"],
                mode="w",
                samplerate=sample_rate,
                channels=channels,
                subtype="FLOAT",
                format="WAV",
            ) as dialogue_file,
            sf.SoundFile(
                partials["background"],
                mode="w",
                samplerate=sample_rate,
                channels=channels,
                subtype="FLOAT",
                format="WAV",
            ) as background_file,
        ):
            offset = 0
            while offset < frame_count:
                if should_cancel():
                    raise SeparationCancelled(
                        "separation cancelled"
                    )
                block_frames = min(
                    io_block_frames,
                    frame_count - offset,
                )
                source = source_file.read(
                    block_frames,
                    dtype="float32",
                    always_2d=True,
                )
                if source.shape != (block_frames, channels):
                    raise RuntimeError(
                        "source ended before the declared frame count"
                    )
                raw_weights = np.asarray(
                    weights[offset : offset + block_frames]
                )
                if np.any(raw_weights <= 0):
                    raise RuntimeError(
                        "overlap-add left uncovered source frames"
                    )
                block_weights = np.maximum(
                    raw_weights,
                    np.finfo(np.float32).eps,
                )
                dialogue = np.asarray(
                    accumulated[offset : offset + block_frames]
                ) / block_weights
                dialogue = np.asarray(
                    dialogue,
                    dtype=np.float32,
                )
                background = source - dialogue
                if not (
                    np.isfinite(source).all()
                    and np.isfinite(dialogue).all()
                    and np.isfinite(background).all()
                ):
                    raise RuntimeError(
                        "separation output contains non-finite samples"
                    )
                reconstruction_error = float(
                    np.max(
                        np.abs(
                            dialogue + background - source
                        )
                    )
                )
                if reconstruction_error > 1e-6:
                    raise RuntimeError(
                        "residual reconstruction failed before "
                        f"encoding: {reconstruction_error}"
                    )
                dialogue_file.write(dialogue)
                background_file.write(background)
                offset += block_frames
                progress(
                    "encoding",
                    0.82 + 0.13 * offset / frame_count,
                    "正在流式写入无损 WAV",
                )

        for role, path in partials.items():
            info = sf.info(path)
            if (
                info.samplerate != sample_rate
                or info.channels != channels
                or info.frames != frame_count
            ):
                raise RuntimeError(
                    f"{role} artifact metadata does not match source"
                )

        progress(
            "validating",
            0.96,
            "正在流式校验时长、声道和重构误差",
        )
        with (
            sf.SoundFile(source_path, mode="r") as source_file,
            sf.SoundFile(
                partials["dialogue"],
                mode="r",
            ) as dialogue_file,
            sf.SoundFile(
                partials["background"],
                mode="r",
            ) as background_file,
        ):
            validated_frames = 0
            while validated_frames < frame_count:
                if should_cancel():
                    raise SeparationCancelled(
                        "separation cancelled"
                    )
                block_frames = min(
                    io_block_frames,
                    frame_count - validated_frames,
                )
                source = source_file.read(
                    block_frames,
                    dtype="float32",
                    always_2d=True,
                )
                dialogue = dialogue_file.read(
                    block_frames,
                    dtype="float32",
                    always_2d=True,
                )
                background = background_file.read(
                    block_frames,
                    dtype="float32",
                    always_2d=True,
                )
                if not (
                    source.shape
                    == dialogue.shape
                    == background.shape
                    == (block_frames, channels)
                ):
                    raise RuntimeError(
                        "encoded separation artifacts ended early"
                    )
                encoded_error = float(
                    np.max(
                        np.abs(
                            dialogue + background - source
                        )
                    )
                )
                if encoded_error > 1e-6:
                    raise RuntimeError(
                        "residual reconstruction failed after "
                        f"encoding: {encoded_error}"
                    )
                validated_frames += block_frames
                progress(
                    "validating",
                    0.96
                    + 0.04 * validated_frames / frame_count,
                    "正在流式校验时长、声道和重构误差",
                )

        artifacts = _streaming_artifact_metadata(
            partials=partials,
            finals=finals,
            sample_rate=sample_rate,
            channels=channels,
            frame_count=frame_count,
            should_cancel=should_cancel,
        )
        if should_cancel():
            raise SeparationCancelled("separation cancelled before publish")
        for role in ("dialogue", "background"):
            os.replace(partials[role], finals[role])
    except Exception:
        for path in [*partials.values(), *finals.values()]:
            path.unlink(missing_ok=True)
        raise

    return artifacts


def publish_artifacts(
    *,
    output_dir: Path,
    source: np.ndarray,
    dialogue: np.ndarray,
    background: np.ndarray,
    sample_rate: int,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (
        dialogue.shape != source.shape
        or background.shape != source.shape
    ):
        raise RuntimeError(
            "separation outputs must match decoded source shape"
        )
    if not all(
        np.isfinite(audio).all()
        for audio in (source, dialogue, background)
    ):
        raise RuntimeError("separation output contains non-finite samples")
    reconstruction_error = float(
        np.max(np.abs(dialogue + background - source))
    )
    if reconstruction_error > 1e-6:
        raise RuntimeError(
            "residual reconstruction failed before encoding: "
            f"{reconstruction_error}"
        )

    partials = {
        "dialogue": output_dir / "dialogue.partial.wav",
        "background": output_dir / "background.partial.wav",
    }
    finals = {
        "dialogue": output_dir / "dialogue.wav",
        "background": output_dir / "background.wav",
    }
    for path in [*partials.values(), *finals.values()]:
        path.unlink(missing_ok=True)

    try:
        sf.write(
            partials["dialogue"],
            dialogue,
            sample_rate,
            subtype="FLOAT",
        )
        sf.write(
            partials["background"],
            background,
            sample_rate,
            subtype="FLOAT",
        )
        decoded = {}
        for role, path in partials.items():
            info = sf.info(path)
            if (
                info.samplerate != sample_rate
                or info.channels != source.shape[1]
                or info.frames != source.shape[0]
            ):
                raise RuntimeError(
                    f"{role} artifact metadata does not match source"
                )
            decoded[role], _ = sf.read(
                path,
                dtype="float32",
                always_2d=True,
            )
        encoded_error = float(
            np.max(
                np.abs(
                    decoded["dialogue"]
                    + decoded["background"]
                    - source
                )
            )
        )
        if encoded_error > 1e-6:
            raise RuntimeError(
                "residual reconstruction failed after encoding: "
                f"{encoded_error}"
            )

        for role in ("dialogue", "background"):
            os.replace(partials[role], finals[role])
    except Exception:
        for path in [*partials.values(), *finals.values()]:
            path.unlink(missing_ok=True)
        raise

    artifacts = []
    for role in ("dialogue", "background"):
        path = finals[role]
        artifacts.append(
            {
                "id": uuid.uuid4().hex,
                "role": role,
                "filename": path.name,
                "content_type": "audio/wav",
                "size_bytes": path.stat().st_size,
                "sample_rate": sample_rate,
                "channels": source.shape[1],
                "frame_count": source.shape[0],
                "sha256": _sha256(path),
                "_path": str(path),
            }
        )
    return artifacts


class TigerDNRHandler:
    def __init__(
        self,
        *,
        test_mode: bool = False,
        model_sample_rate: int = 44100,
        chunk_seconds: float = 6.0,
        overlap_fraction: float = 0.5,
        infer_chunk: Callable[[np.ndarray], np.ndarray] | None = None,
        io_block_frames: int = 262144,
    ):
        if not 0 <= overlap_fraction < 1:
            raise ValueError(
                "overlap_fraction must be greater than or equal to 0 "
                "and less than 1"
            )
        self.test_mode = test_mode
        self.model_sample_rate = model_sample_rate
        self.chunk_seconds = chunk_seconds
        self.overlap_fraction = overlap_fraction
        self.io_block_frames = max(1, int(io_block_frames))
        self.hf_repo_id = os.environ.get(
            "TIGER_DNR_HF_REPO_ID",
            "JusperLee/TIGER-DnR",
        )
        self.hf_revision = os.environ.get(
            "TIGER_DNR_HF_REVISION",
            "b7a59560bbca10febbcd46fb01600f868e587f57",
        )
        self.model_dir = Path(
            os.environ.get(
                "TIGER_DNR_MODEL_DIR",
                "models/tiger/TIGER-DnR",
            )
        )
        self.device = os.environ.get(
            "TIGER_DNR_DEVICE",
            "cuda:0",
        )
        self._model = None
        self._inference_lock = threading.Lock()
        self._custom_infer_chunk = infer_chunk

    def separate_file(
        self,
        *,
        source_path: Path,
        output_dir: Path,
        progress: PipelineProgressCallback,
        should_cancel: CancelCallback,
    ) -> list[dict]:
        output_dir.mkdir(parents=True, exist_ok=True)
        progress("decoding", 0.01, "正在准备流式音频解码")
        prepared_path, info, remove_prepared = (
            _prepare_stream_source(
                source_path,
                work_dir=output_dir,
                should_cancel=should_cancel,
            )
        )
        sample_rate = int(info.samplerate)
        channels = int(info.channels)
        frame_count = int(info.frames)
        chunk_frames = max(
            1,
            round(self.chunk_seconds * sample_rate),
        )
        overlap_frames = round(
            chunk_frames * self.overlap_fraction
        )
        hop_frames = max(1, chunk_frames - overlap_frames)
        model_chunk_frames = max(
            1,
            round(
                self.chunk_seconds * self.model_sample_rate
            ),
        )
        tail_start = max(
            frame_count - chunk_frames,
            0,
        )
        regular_starts = range(
            0,
            tail_start + 1,
            hop_frames,
        )
        regular_last = regular_starts[-1]
        append_tail = (
            regular_last + chunk_frames < frame_count
        )
        starts = (
            chain(regular_starts, (tail_start,))
            if append_tail
            else iter(regular_starts)
        )
        total_chunks = len(regular_starts) + int(
            append_tail
        )

        accumulated_path = output_dir / "dialogue.accum.f32"
        weights_path = output_dir / "dialogue.weights.f32"
        accumulated_path.unlink(missing_ok=True)
        weights_path.unlink(missing_ok=True)
        accumulated = None
        weights = None
        try:
            if should_cancel():
                raise SeparationCancelled(
                    "separation cancelled"
                )
            accumulated = _create_fresh_zero_memmap(
                accumulated_path,
                shape=(frame_count, channels),
                should_cancel=should_cancel,
            )
            weights = _create_fresh_zero_memmap(
                weights_path,
                shape=(frame_count, 1),
                should_cancel=should_cancel,
            )

            with sf.SoundFile(
                prepared_path,
                mode="r",
            ) as source_file:
                for index, start in enumerate(starts):
                    if should_cancel():
                        raise SeparationCancelled(
                            "separation cancelled"
                        )
                    end = min(
                        start + chunk_frames,
                        frame_count,
                    )
                    valid_frames = end - start
                    source_file.seek(start)
                    chunk = source_file.read(
                        valid_frames,
                        dtype="float32",
                        always_2d=True,
                    )
                    if chunk.shape != (
                        valid_frames,
                        channels,
                    ):
                        raise RuntimeError(
                            "source ended before the declared "
                            "frame count"
                        )
                    if not np.isfinite(chunk).all():
                        raise RuntimeError(
                            "decoded source contains non-finite "
                            "samples"
                        )
                    if valid_frames < chunk_frames:
                        chunk = np.pad(
                            chunk,
                            (
                                (
                                    0,
                                    chunk_frames
                                    - valid_frames,
                                ),
                                (0, 0),
                            ),
                        )
                    model_chunk = _resample_audio(
                        chunk,
                        sample_rate,
                        self.model_sample_rate,
                        target_frames=model_chunk_frames,
                    )
                    with self._inference_lock:
                        estimated = self._infer_chunk(
                            model_chunk
                        )
                    estimated = np.asarray(
                        estimated,
                        dtype=np.float32,
                    )
                    if estimated.shape != model_chunk.shape:
                        raise RuntimeError(
                            "TIGER-DnR dialogue output shape "
                            "does not match input chunk: "
                            f"{estimated.shape} != "
                            f"{model_chunk.shape}"
                        )
                    estimated = _resample_audio(
                        estimated,
                        self.model_sample_rate,
                        sample_rate,
                        target_frames=chunk_frames,
                    )[:valid_frames]

                    window = np.ones(
                        (valid_frames, 1),
                        dtype=np.float32,
                    )
                    fade_frames = min(
                        overlap_frames,
                        valid_frames,
                    )
                    if fade_frames and start > 0:
                        window[:fade_frames, 0] = np.linspace(
                            0.0,
                            1.0,
                            fade_frames,
                            endpoint=False,
                            dtype=np.float32,
                        )
                    if fade_frames and end < frame_count:
                        window[-fade_frames:, 0] = np.linspace(
                            1.0,
                            0.0,
                            fade_frames,
                            endpoint=False,
                            dtype=np.float32,
                        )
                    accumulated[start:end] += (
                        estimated * window
                    )
                    weights[start:end] += window
                    progress(
                        "separating",
                        0.05
                        + 0.75
                        * (index + 1)
                        / total_chunks,
                        "正在分块提取对白",
                    )
            accumulated.flush()
            weights.flush()
            return _publish_streaming_artifacts(
                output_dir=output_dir,
                source_path=prepared_path,
                accumulated=accumulated,
                weights=weights,
                sample_rate=sample_rate,
                channels=channels,
                frame_count=frame_count,
                io_block_frames=self.io_block_frames,
                progress=progress,
                should_cancel=should_cancel,
            )
        finally:
            if accumulated is not None:
                accumulated.flush()
                accumulated._mmap.close()
                del accumulated
            if weights is not None:
                weights.flush()
                weights._mmap.close()
                del weights
            accumulated_path.unlink(missing_ok=True)
            weights_path.unlink(missing_ok=True)
            if remove_prepared:
                prepared_path.unlink(missing_ok=True)

    def health(self) -> dict:
        return {
            "status": "ok",
            "model": "tiger-dnr",
            "hfRepoId": self.hf_repo_id,
            "hfRevision": self.hf_revision,
            "device": self.device,
            "ready": self.test_mode or self._model is not None,
            "modelSampleRate": self.model_sample_rate,
            "chunkSeconds": self.chunk_seconds,
            "overlapFraction": self.overlap_fraction,
            "capabilities": {
                "separation": True,
                "asyncJobs": True,
                "artifactRoles": [
                    "dialogue",
                    "background",
                ],
            },
        }

    def estimate_dialogue(
        self,
        source: np.ndarray,
        *,
        source_sample_rate: int,
        progress: ProgressCallback,
        should_cancel: CancelCallback,
    ) -> np.ndarray:
        source = np.asarray(source, dtype=np.float32)
        if source.ndim != 2 or source.shape[0] == 0:
            raise ValueError(
                "decoded source must contain frames and channels"
            )
        if not np.isfinite(source).all():
            raise RuntimeError("decoded source contains non-finite samples")

        model_audio = _resample_audio(
            source,
            source_sample_rate,
            self.model_sample_rate,
        )
        chunk_frames = max(
            1,
            round(self.chunk_seconds * self.model_sample_rate),
        )
        overlap_frames = round(
            chunk_frames * self.overlap_fraction
        )
        hop_frames = max(1, chunk_frames - overlap_frames)
        total_frames = model_audio.shape[0]
        last_regular_start = max(total_frames - chunk_frames, 0)
        starts = list(
            range(0, last_regular_start + 1, hop_frames)
        )
        if not starts:
            starts = [0]
        if starts[-1] + chunk_frames < total_frames:
            starts.append(last_regular_start)

        accumulated = np.zeros_like(model_audio, dtype=np.float32)
        weights = np.zeros((total_frames, 1), dtype=np.float32)

        for index, start in enumerate(starts):
            if should_cancel():
                raise SeparationCancelled("separation cancelled")
            end = min(start + chunk_frames, total_frames)
            valid_frames = end - start
            chunk = model_audio[start:end]
            if valid_frames < chunk_frames:
                chunk = np.pad(
                    chunk,
                    ((0, chunk_frames - valid_frames), (0, 0)),
                )

            with self._inference_lock:
                estimated = self._infer_chunk(chunk)
            estimated = np.asarray(estimated, dtype=np.float32)
            if estimated.shape != chunk.shape:
                raise RuntimeError(
                    "TIGER-DnR dialogue output shape does not match input "
                    f"chunk: {estimated.shape} != {chunk.shape}"
                )
            estimated = estimated[:valid_frames]

            window = np.ones((valid_frames, 1), dtype=np.float32)
            fade_frames = min(overlap_frames, valid_frames)
            if fade_frames and start > 0:
                window[:fade_frames, 0] = np.linspace(
                    0.0,
                    1.0,
                    fade_frames,
                    endpoint=False,
                    dtype=np.float32,
                )
            if fade_frames and end < total_frames:
                window[-fade_frames:, 0] = np.linspace(
                    1.0,
                    0.0,
                    fade_frames,
                    endpoint=False,
                    dtype=np.float32,
                )
            accumulated[start:end] += estimated * window
            weights[start:end] += window
            progress((index + 1) / len(starts))

        model_dialogue = accumulated / np.maximum(
            weights,
            np.finfo(np.float32).eps,
        )
        dialogue = _resample_audio(
            model_dialogue,
            self.model_sample_rate,
            source_sample_rate,
            target_frames=source.shape[0],
        )
        if dialogue.shape != source.shape:
            raise RuntimeError(
                "resampled dialogue does not match decoded source shape"
            )
        return np.ascontiguousarray(dialogue, dtype=np.float32)

    def _infer_chunk(self, chunk: np.ndarray) -> np.ndarray:
        if self._custom_infer_chunk is not None:
            return self._custom_infer_chunk(chunk)
        if self.test_mode:
            delay = float(
                os.environ.get(
                    "TIGER_DNR_TEST_CHUNK_DELAY",
                    "0",
                )
            )
            if delay > 0:
                time.sleep(delay)
            return chunk * 0.25
        return self._infer_model_chunk(chunk)

    def _load_model(self):
        if self._model is not None:
            return self._model
        import torch
        import look2hear.models

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(
                "TIGER-DnR is configured for CUDA, but CUDA is unavailable"
            )
        self.model_dir.mkdir(parents=True, exist_ok=True)
        model = look2hear.models.TIGERDNR.from_pretrained(
            self.hf_repo_id,
            cache_dir=str(self.model_dir),
            revision=self.hf_revision,
        )
        model.to(torch.device(self.device))
        model.eval()
        self._model = model
        return model

    def _infer_model_chunk(
        self,
        chunk: np.ndarray,
    ) -> np.ndarray:
        import torch

        model = self._load_model()
        tensor = torch.from_numpy(
            np.ascontiguousarray(chunk.T)
        ).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            tracks = model.dialog(tensor)
            batch_size, channels = tensor.shape[:2]
            dialogue = tracks[:, 2, :].reshape(
                batch_size,
                channels,
                -1,
            )
        result = dialogue.detach().float().cpu().numpy()
        while result.ndim > 2 and result.shape[0] == 1:
            result = result[0]
        if result.ndim == 1:
            result = result[None, :]
        if (
            result.ndim != 2
            or result.shape[0] != chunk.shape[1]
        ):
            raise RuntimeError(
                "Unexpected TIGER-DnR dialogue tensor shape: "
                f"{result.shape}"
            )
        return np.ascontiguousarray(result.T, dtype=np.float32)
