def test_synthesize_request_supports_protocol_fields():
    from bobogen_protocol.models import SynthesizeRequest

    request = SynthesizeRequest.model_validate(
        {
            "text": "你好",
            "voice_id": "default",
            "language": "zh",
            "parameters": {
                "speed": 1.0,
                "emotion": "happy",
                "instruction": "温柔一点",
                "extra": {"seed": 1},
            },
            "output": {"format": "wav", "sample_rate": 24000},
        }
    )

    assert request.text == "你好"
    assert request.parameters.emotion == "happy"
    assert request.output.sample_rate == 24000


def test_clone_request_supports_emotion_and_reference_metadata():
    from bobogen_protocol.models import CloneRequest

    request = CloneRequest.model_validate(
        {
            "name": "测试音色",
            "language": "zh",
            "text": "这是一段参考文本",
            "emotion": "sad",
            "metadata": {"source": "unit-test"},
        }
    )

    assert request.name == "测试音色"
    assert request.emotion == "sad"
    assert request.metadata["source"] == "unit-test"


def test_protocol_supports_design_and_clone_status_models():
    from bobogen_protocol.models import CloneStatusResponse, DesignRequest, DesignResponse, HealthResponse

    design_request = DesignRequest.model_validate(
        {
            "base_voice_id": "default",
            "name": "温柔女声",
            "parameters": {"extra": {"style": "gentle"}},
        }
    )
    design_response = DesignResponse.model_validate(
        {"voice_id": "designed_001", "name": "温柔女声", "status": "ready"}
    )
    clone_status = CloneStatusResponse.model_validate(
        {"task_id": "clone_task_001", "status": "ready", "voice_id": "voice_001", "name": "我的声音"}
    )
    health = HealthResponse.model_validate({"status": "ok", "model": "GPT-SoVITS", "version": "1.0.0"})

    assert design_request.parameters["extra"]["style"] == "gentle"
    assert design_response.voice_id == "designed_001"
    assert clone_status.task_id == "clone_task_001"
    assert health.model == "GPT-SoVITS"


def test_generate_request_supports_tts_speech_and_file_inputs():
    from bobogen_protocol.models import GenerateRequest

    request = GenerateRequest.model_validate(
        {
            "model": "f5_tts",
            "task": "tts.speech",
            "input": {
                "text": "你好",
                "voice": "f5-default",
                "language": "zh",
            },
            "parameters": {
                "reference_audio": {"kind": "upload", "field": "ref_audio"},
                "emotion_reference_audio": {"kind": "data_uri", "data": "data:audio/wav;base64,UklGRg=="},
                "speed": 1.1,
            },
            "output": {"format": "wav", "sample_rate": 24000},
        }
    )

    assert request.model == "f5_tts"
    assert request.task == "tts.speech"
    assert request.input["voice"] == "f5-default"
    assert request.parameters["reference_audio"].kind == "upload"
    assert request.parameters["emotion_reference_audio"].kind == "data_uri"
    assert request.output.sample_rate == 24000


def test_model_info_describes_generation_capabilities():
    from bobogen_protocol.models import ModelInfo

    model = ModelInfo.model_validate(
        {
            "id": "f5_tts",
            "name": "F5-TTS",
            "provider_id": "f5_tts",
            "tasks": ["tts.speech"],
            "outputs": ["audio/wav"],
            "enabled": True,
            "voices": [{"voice_id": "f5-default", "name": "Default"}],
            "capabilities": {"reference_audio": True},
        }
    )

    assert model.id == "f5_tts"
    assert model.tasks == ["tts.speech"]
    assert model.outputs == ["audio/wav"]
    assert model.voices[0].voice_id == "f5-default"


def test_job_response_serializes_progress_and_two_public_artifact_roles():
    from bobogen_protocol.models import JobResponse

    job = JobResponse.model_validate(
        {
            "id": "opaque-job-id",
            "model": "tiger-dnr",
            "task": "audio.separate",
            "status": "succeeded",
            "progress": {
                "phase": "validating",
                "fraction": 1.0,
                "message": "输出校验完成",
            },
            "artifacts": [
                {
                    "id": "opaque-dialogue-id",
                    "role": "dialogue",
                    "filename": "dialogue.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1024,
                    "sample_rate": 44100,
                    "channels": 2,
                    "frame_count": 44100,
                    "sha256": "a" * 64,
                },
                {
                    "id": "opaque-background-id",
                    "role": "background",
                    "filename": "background.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1024,
                    "sample_rate": 44100,
                    "channels": 2,
                    "frame_count": 44100,
                    "sha256": "b" * 64,
                },
            ],
        }
    )

    payload = job.model_dump(mode="json")
    assert payload["progress"] == {
        "phase": "validating",
        "fraction": 1.0,
        "message": "输出校验完成",
    }
    assert [artifact["role"] for artifact in payload["artifacts"]] == [
        "dialogue",
        "background",
    ]


def test_job_progress_rejects_fraction_outside_zero_to_one():
    import pytest
    from pydantic import ValidationError

    from bobogen_protocol.models import JobProgress

    with pytest.raises(ValidationError):
        JobProgress.model_validate({"phase": "separating", "fraction": 1.01})


def test_job_response_rejects_unknown_status_and_artifact_role():
    import pytest
    from pydantic import ValidationError

    from bobogen_protocol.models import JobArtifact, JobResponse

    with pytest.raises(ValidationError):
        JobResponse.model_validate(
            {
                "id": "job",
                "model": "tiger-dnr",
                "task": "audio.separate",
                "status": "done",
                "progress": {"phase": "separating", "fraction": 0.5},
            }
        )

    with pytest.raises(ValidationError):
        JobArtifact.model_validate(
            {
                "id": "artifact",
                "role": "music",
                "filename": "music.wav",
                "content_type": "audio/wav",
                "size_bytes": 1,
                "sample_rate": 44100,
                "channels": 2,
                "frame_count": 1,
                "sha256": "a" * 64,
            }
        )
