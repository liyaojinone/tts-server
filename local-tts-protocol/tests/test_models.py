def test_synthesize_request_supports_protocol_fields():
    from local_tts_protocol.models import SynthesizeRequest

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
    from local_tts_protocol.models import CloneRequest

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
    from local_tts_protocol.models import CloneStatusResponse, DesignRequest, DesignResponse, HealthResponse

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
