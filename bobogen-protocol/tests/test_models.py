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
            "model": "local_f5_tts",
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

    assert request.model == "local_f5_tts"
    assert request.task == "tts.speech"
    assert request.input["voice"] == "f5-default"
    assert request.parameters["reference_audio"].kind == "upload"
    assert request.parameters["emotion_reference_audio"].kind == "data_uri"
    assert request.output.sample_rate == 24000


def test_model_info_describes_generation_capabilities():
    from bobogen_protocol.models import ModelInfo

    model = ModelInfo.model_validate(
        {
            "id": "local_f5_tts",
            "name": "F5-TTS",
            "provider_id": "local_f5_tts",
            "tasks": ["tts.speech"],
            "outputs": ["audio/wav"],
            "enabled": True,
            "voices": [{"voice_id": "f5-default", "name": "Default"}],
            "capabilities": {"reference_audio": True},
        }
    )

    assert model.id == "local_f5_tts"
    assert model.tasks == ["tts.speech"]
    assert model.outputs == ["audio/wav"]
    assert model.voices[0].voice_id == "f5-default"
