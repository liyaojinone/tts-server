import threading

import numpy as np
import pytest
import soundfile as sf


def test_health_explicitly_reports_separation_capability():
    from app.handler import TigerDNRHandler

    health = TigerDNRHandler(test_mode=True).health()

    assert health["capabilities"]["separation"] is True
    assert health["capabilities"]["asyncJobs"] is True
    assert health["capabilities"]["artifactRoles"] == [
        "dialogue",
        "background",
    ]


def test_streaming_file_separation_uses_bounded_reads_and_reconstructs_source(
    tmp_path,
    monkeypatch,
):
    from app.handler import TigerDNRHandler

    source = np.linspace(
        -0.8,
        0.8,
        80,
        dtype=np.float32,
    ).reshape(40, 2)
    source_path = tmp_path / "source.wav"
    sf.write(source_path, source, 8, subtype="FLOAT")
    original_read = sf.SoundFile.read
    read_sizes = []

    def tracked_read(sound_file, frames=-1, *args, **kwargs):
        read_sizes.append(frames)
        assert frames != -1
        assert frames <= 8
        return original_read(
            sound_file,
            frames,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(sf.SoundFile, "read", tracked_read)
    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        overlap_fraction=0.5,
        infer_chunk=lambda chunk: chunk * 0.25,
        io_block_frames=8,
    )
    stages = []

    artifacts = handler.separate_file(
        source_path=source_path,
        output_dir=tmp_path / "outputs",
        progress=lambda phase, fraction, _message: stages.append(
            (phase, fraction)
        ),
        should_cancel=lambda: False,
    )

    assert read_sizes
    assert [item["role"] for item in artifacts] == [
        "dialogue",
        "background",
    ]
    output_dir = tmp_path / "outputs"
    with sf.SoundFile(output_dir / "dialogue.wav") as wav:
        dialogue = original_read(
            wav,
            wav.frames,
            dtype="float32",
            always_2d=True,
        )
    with sf.SoundFile(output_dir / "background.wav") as wav:
        background = original_read(
            wav,
            wav.frames,
            dtype="float32",
            always_2d=True,
        )
    np.testing.assert_allclose(
        dialogue + background,
        source,
        atol=1e-6,
    )
    assert artifacts[0]["frame_count"] == source.shape[0]
    assert artifacts[1]["frame_count"] == source.shape[0]
    assert stages[0][0] == "decoding"
    assert stages[-1] == ("validating", 1.0)
    assert not list((tmp_path / "outputs").glob("*.f32"))


def test_streaming_memmaps_use_fresh_zero_files_without_full_slice_writes(
    tmp_path,
    monkeypatch,
):
    from app import handler as handler_module

    original_memmap = handler_module.np.memmap
    full_slice_writes = []
    modes = []

    class TrackedMemmap:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __getitem__(self, key):
            return self._inner[key]

        def __setitem__(self, key, value):
            if (
                isinstance(key, slice)
                and key.start is None
                and key.stop is None
                and key.step is None
            ):
                full_slice_writes.append(key)
            self._inner[key] = value

    def tracked_memmap(*args, **kwargs):
        modes.append(kwargs.get("mode"))
        return TrackedMemmap(
            original_memmap(*args, **kwargs)
        )

    monkeypatch.setattr(
        handler_module.np,
        "memmap",
        tracked_memmap,
    )
    source = np.linspace(
        -0.8,
        0.8,
        24,
        dtype=np.float32,
    ).reshape(12, 2)
    source_path = tmp_path / "source.wav"
    sf.write(source_path, source, 8, subtype="FLOAT")
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "dialogue.accum.f32").write_bytes(
        b"\xff" * (source.size * 4)
    )
    (output_dir / "dialogue.weights.f32").write_bytes(
        b"\xff" * (source.shape[0] * 4)
    )
    handler = handler_module.TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=0.5,
        overlap_fraction=0.5,
        infer_chunk=lambda chunk: chunk * 0.25,
        io_block_frames=4,
    )

    handler.separate_file(
        source_path=source_path,
        output_dir=output_dir,
        progress=lambda _phase, _fraction, _message: None,
        should_cancel=lambda: False,
    )

    dialogue, _ = sf.read(
        output_dir / "dialogue.wav",
        dtype="float32",
        always_2d=True,
    )
    background, _ = sf.read(
        output_dir / "background.wav",
        dtype="float32",
        always_2d=True,
    )
    assert modes == ["r+", "r+"]
    assert full_slice_writes == []
    np.testing.assert_allclose(
        dialogue,
        source * 0.25,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        dialogue + background,
        source,
        atol=1e-6,
    )


def test_streaming_file_cancels_before_allocating_memmaps(
    tmp_path,
    monkeypatch,
):
    from app import handler as handler_module

    source_path = tmp_path / "source.wav"
    sf.write(
        source_path,
        np.ones((8, 1), dtype=np.float32),
        8,
        subtype="FLOAT",
    )
    memmap_calls = 0

    def unexpected_memmap(*_args, **_kwargs):
        nonlocal memmap_calls
        memmap_calls += 1
        raise AssertionError(
            "cancelled separation must not allocate memmaps"
        )

    monkeypatch.setattr(
        handler_module.np,
        "memmap",
        unexpected_memmap,
    )
    handler = handler_module.TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        infer_chunk=lambda chunk: chunk,
    )
    output_dir = tmp_path / "outputs"

    with pytest.raises(handler_module.SeparationCancelled):
        handler.separate_file(
            source_path=source_path,
            output_dir=output_dir,
            progress=lambda _phase, _fraction, _message: None,
            should_cancel=lambda: True,
        )

    assert memmap_calls == 0
    assert not list(output_dir.glob("*.f32"))


def test_streaming_file_separation_preserves_prime_frames_across_resampling(
    tmp_path,
):
    from app.handler import TigerDNRHandler

    frame_count = 1009
    source = np.linspace(
        -0.5,
        0.5,
        frame_count * 2,
        dtype=np.float32,
    ).reshape(frame_count, 2)
    source_path = tmp_path / "source-48k.wav"
    sf.write(
        source_path,
        source,
        48000,
        subtype="FLOAT",
    )
    output_dir = tmp_path / "outputs"
    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=44100,
        chunk_seconds=0.005,
        overlap_fraction=0.5,
        infer_chunk=lambda chunk: chunk * 0.25,
        io_block_frames=113,
    )

    artifacts = handler.separate_file(
        source_path=source_path,
        output_dir=output_dir,
        progress=lambda _phase, _fraction, _message: None,
        should_cancel=lambda: False,
    )

    dialogue, dialogue_rate = sf.read(
        output_dir / "dialogue.wav",
        dtype="float32",
        always_2d=True,
    )
    background, background_rate = sf.read(
        output_dir / "background.wav",
        dtype="float32",
        always_2d=True,
    )
    assert dialogue_rate == background_rate == 48000
    assert dialogue.shape == background.shape == source.shape
    assert all(
        artifact["frame_count"] == frame_count
        for artifact in artifacts
    )
    np.testing.assert_allclose(
        dialogue + background,
        source,
        atol=1e-6,
    )


def test_streaming_publish_cancellation_during_hash_removes_all_outputs(
    tmp_path,
):
    from app.handler import SeparationCancelled, TigerDNRHandler

    source_path = tmp_path / "source.wav"
    sf.write(
        source_path,
        np.ones((32, 1), dtype=np.float32),
        8,
        subtype="FLOAT",
    )
    cancel = False

    def progress(phase, fraction, _message):
        nonlocal cancel
        if phase == "validating" and fraction == 1.0:
            cancel = True

    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        infer_chunk=lambda chunk: chunk * 0.25,
        io_block_frames=8,
    )
    output_dir = tmp_path / "outputs"

    with pytest.raises(SeparationCancelled):
        handler.separate_file(
            source_path=source_path,
            output_dir=output_dir,
            progress=progress,
            should_cancel=lambda: cancel,
        )

    assert not list(output_dir.glob("*.wav"))
    assert not list(output_dir.glob("*.f32"))


def test_chunked_dialogue_estimation_preserves_exact_source_shape_and_uses_overlap():
    from app.handler import TigerDNRHandler

    calls = []

    def fake_infer(chunk):
        calls.append(chunk.copy())
        return chunk * 0.25

    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        overlap_fraction=0.5,
        infer_chunk=fake_infer,
    )
    source = np.linspace(-0.8, 0.8, 20, dtype=np.float32)[:, None]

    dialogue = handler.estimate_dialogue(
        source,
        source_sample_rate=8,
        progress=lambda _fraction: None,
        should_cancel=lambda: False,
    )

    assert dialogue.shape == source.shape
    np.testing.assert_allclose(dialogue, source * 0.25, atol=1e-6)
    assert len(calls) > 1
    assert all(chunk.shape == (8, 1) for chunk in calls)


def test_residual_background_reconstructs_decoded_source():
    from app.handler import residual_background

    source = np.array([[0.8, -0.5], [0.1, 0.25]], dtype=np.float32)
    dialogue = np.array([[0.3, -0.2], [0.05, 0.1]], dtype=np.float32)

    background = residual_background(source, dialogue)

    np.testing.assert_allclose(dialogue + background, source, atol=1e-7)


def test_handler_checks_cancellation_between_chunks():
    from app.handler import SeparationCancelled, TigerDNRHandler

    calls = 0

    def fake_infer(chunk):
        nonlocal calls
        calls += 1
        return chunk

    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        overlap_fraction=0.5,
        infer_chunk=fake_infer,
    )
    source = np.ones((24, 1), dtype=np.float32)

    try:
        handler.estimate_dialogue(
            source,
            source_sample_rate=8,
            progress=lambda _fraction: None,
            should_cancel=lambda: calls >= 1,
        )
    except SeparationCancelled:
        pass
    else:
        raise AssertionError("expected cancellation between chunks")

    assert calls == 1


def test_atomic_artifact_publish_validates_two_wavs_before_exposing_them(tmp_path):
    from app.handler import publish_artifacts

    source = np.array([[0.8], [0.1], [-0.2], [0.0]], dtype=np.float32)
    dialogue = source * 0.25
    background = source - dialogue

    artifacts = publish_artifacts(
        output_dir=tmp_path,
        source=source,
        dialogue=dialogue,
        background=background,
        sample_rate=8000,
    )

    assert [item["role"] for item in artifacts] == ["dialogue", "background"]
    assert not list(tmp_path.glob("*.partial.wav"))
    for artifact in artifacts:
        path = tmp_path / artifact["filename"]
        assert path.exists()
        info = sf.info(path)
        assert info.samplerate == 8000
        assert info.channels == 1
        assert info.frames == source.shape[0]

    written_dialogue, _ = sf.read(
        tmp_path / "dialogue.wav",
        dtype="float32",
        always_2d=True,
    )
    written_background, _ = sf.read(
        tmp_path / "background.wav",
        dtype="float32",
        always_2d=True,
    )
    np.testing.assert_allclose(
        written_dialogue + written_background,
        source,
        atol=2 / 32768,
    )


def test_single_gpu_inference_lock_serializes_model_calls():
    from app.handler import TigerDNRHandler

    active = 0
    max_active = 0
    guard = threading.Lock()

    def fake_infer(chunk):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        import time

        time.sleep(0.03)
        with guard:
            active -= 1
        return chunk

    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
        chunk_seconds=1.0,
        overlap_fraction=0.5,
        infer_chunk=fake_infer,
    )
    source = np.ones((8, 1), dtype=np.float32)

    threads = [
        threading.Thread(
            target=handler.estimate_dialogue,
            kwargs={
                "source": source,
                "source_sample_rate": 8,
                "progress": lambda _fraction: None,
                "should_cancel": lambda: False,
            },
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_real_backend_runs_only_dialogue_decoder_and_selects_dialogue_track():
    import torch

    from app.handler import TigerDNRHandler

    class FakeDialogueDecoder:
        def __call__(self, tensor):
            assert tensor.shape == (1, 2, 8)
            flattened = tensor.reshape(2, 8)
            return torch.stack(
                [
                    torch.zeros_like(flattened),
                    torch.zeros_like(flattened),
                    flattened * 0.25,
                ],
                dim=1,
            )

    class FakeModel:
        dialog = FakeDialogueDecoder()

        def __call__(self, _tensor):
            raise AssertionError(
                "full three-decoder forward must not run"
            )

    handler = TigerDNRHandler(
        test_mode=False,
        model_sample_rate=8,
    )
    handler.device = "cpu"
    handler._model = FakeModel()
    chunk = np.arange(16, dtype=np.float32).reshape(8, 2)

    dialogue = handler._infer_model_chunk(chunk)

    np.testing.assert_allclose(dialogue, chunk * 0.25)


def test_model_download_uses_configured_huggingface_revision(
    monkeypatch,
    tmp_path,
):
    import sys
    from types import ModuleType

    from app.handler import TigerDNRHandler

    captured = {}

    class FakeModel:
        def to(self, device):
            captured["device"] = str(device)
            return self

        def eval(self):
            captured["eval"] = True
            return self

    def fake_from_pretrained(repo_id, **kwargs):
        captured["repo_id"] = repo_id
        captured.update(kwargs)
        return FakeModel()

    fake_models = ModuleType("look2hear.models")
    fake_models.TIGERDNR = type(
        "FakeTigerDNR",
        (),
        {"from_pretrained": staticmethod(fake_from_pretrained)},
    )
    fake_look2hear = ModuleType("look2hear")
    fake_look2hear.models = fake_models
    monkeypatch.setitem(sys.modules, "look2hear", fake_look2hear)
    monkeypatch.setitem(sys.modules, "look2hear.models", fake_models)
    monkeypatch.setenv(
        "TIGER_DNR_HF_REVISION",
        "pinned-test-revision",
    )
    monkeypatch.setenv(
        "TIGER_DNR_MODEL_DIR",
        str(tmp_path / "model-cache"),
    )
    handler = TigerDNRHandler(test_mode=False)
    handler.device = "cpu"

    handler._load_model()

    assert captured["repo_id"] == "JusperLee/TIGER-DnR"
    assert captured["revision"] == "pinned-test-revision"
    assert captured["cache_dir"] == str(tmp_path / "model-cache")
    assert captured["device"] == "cpu"
    assert captured["eval"] is True
