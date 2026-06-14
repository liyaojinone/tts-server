from app.schemas.synthesize import OutputOptions, SynthesizeParameters, UnifiedSynthesizeRequest


def test_cosyvoice_mapping_uses_openai_compatible_endpoint():
    from app.adapters.cosyvoice import CosyVoiceAdapter

    adapter = CosyVoiceAdapter()
    request = UnifiedSynthesizeRequest(
        text="你好",
        voice_id="中文女",
        language="zh",
        parameters=SynthesizeParameters(speed=1.2, instruction="温柔一点"),
        output=OutputOptions(format="wav", sample_rate=24000),
    )

    mapped = adapter.build_request(request)

    assert mapped.path == "/v1/audio/speech"
    assert mapped.json["input"] == "你好"
    assert mapped.json["voice"] == "中文女"
    assert mapped.json["speed"] == 1.2


def test_f5tts_mapping_uses_tts_endpoint():
    from app.adapters.f5tts import F5TTSAdapter

    adapter = F5TTSAdapter()
    request = UnifiedSynthesizeRequest(
        text="你好",
        voice_id="f5-default",
        language="zh",
        parameters=SynthesizeParameters(
            speed=1.0,
            reference_audio="E:/AiModel/tts/ref.wav",
            reference_text="你好",
            extra={"nfe_step": 16},
        ),
        output=OutputOptions(format="wav", sample_rate=24000),
    )

    mapped = adapter.build_request(request)

    assert mapped.path == "/tts"
    assert mapped.json["text"] == "你好"
    assert mapped.json["ref_audio"] == "E:/AiModel/tts/ref.wav"
    assert mapped.json["ref_text"] == "你好"
    assert mapped.json["nfe_step"] == 16


def test_gptsovits_mapping_uses_tts_endpoint():
    from app.adapters.gptsovits import GPTSoVITSAdapter

    adapter = GPTSoVITSAdapter()
    request = UnifiedSynthesizeRequest(
        text="你好",
        voice_id="nahida",
        language="zh",
        parameters=SynthesizeParameters(
            speed=1.1,
            reference_audio="E:/AiModel/tts/ref.wav",
            reference_text="我是参考文本",
        ),
        output=OutputOptions(format="wav", sample_rate=32000),
    )

    mapped = adapter.build_request(request)

    assert mapped.path == "/tts"
    assert mapped.json["text"] == "你好"
    assert mapped.json["text_lang"] == "zh"
    assert mapped.json["ref_audio_path"] == "E:/AiModel/tts/ref.wav"
    assert mapped.json["prompt_text"] == "我是参考文本"
    assert mapped.json["speed_factor"] == 1.1


def test_indextts_mapping_keeps_emotion_reference_audio_inside_extra():
    from app.adapters.indextts import IndexTTSAdapter

    adapter = IndexTTSAdapter()
    request = UnifiedSynthesizeRequest(
        text="你好",
        voice_id="index-default",
        language="zh",
        parameters=SynthesizeParameters(
            reference_audio="E:/AiModel/tts/speaker.wav",
            reference_text="主参考文本",
            extra={"emotion_reference_audio": "E:/AiModel/tts/emotion.wav"},
        ),
        output=OutputOptions(format="wav", sample_rate=22050),
    )

    mapped = adapter.build_request(request)

    assert mapped.path == "/v1/synthesize"
    assert mapped.json["parameters"]["reference_audio"] == "E:/AiModel/tts/speaker.wav"
    assert mapped.json["parameters"]["reference_text"] == "主参考文本"
    assert mapped.json["parameters"]["extra"]["emotion_reference_audio"] == "E:/AiModel/tts/emotion.wav"
    assert "emotion_reference_audio" not in mapped.json["parameters"]


def test_voxcpm_mapping_keeps_instruction_and_reference_fields():
    from app.adapters.voxcpm import VoxCPMAdapter

    adapter = VoxCPMAdapter()
    request = UnifiedSynthesizeRequest(
        text="你好",
        voice_id="voxcpm2-default",
        language="zh",
        parameters=SynthesizeParameters(
            instruction="成熟男声，稳重",
            reference_audio="E:/AiModel/tts/ref.wav",
            reference_text="这是参考文本",
            extra={"cfg_value": 2.5, "inference_timesteps": 12},
        ),
        output=OutputOptions(format="wav", sample_rate=48000),
    )

    mapped = adapter.build_request(request)

    assert mapped.path == "/v1/synthesize"
    assert mapped.json["parameters"]["instruction"] == "成熟男声，稳重"
    assert mapped.json["parameters"]["reference_audio"] == "E:/AiModel/tts/ref.wav"
    assert mapped.json["parameters"]["reference_text"] == "这是参考文本"
    assert mapped.json["parameters"]["extra"]["cfg_value"] == 2.5
    assert mapped.json["parameters"]["extra"]["inference_timesteps"] == 12


def test_generate_tts_mapping_preserves_extra_model_parameters():
    from app.adapters.indextts import IndexTTSAdapter
    from app.schemas.generate import GenerateRequest

    adapter = IndexTTSAdapter()
    generate_request = GenerateRequest(
        model="local_index_tts",
        task="tts.speech",
        input={"text": "你好", "voice": "index-default", "language": "zh"},
        parameters={
            "reference_audio": "E:/AiModel/tts/speaker.wav",
            "reference_text": "主参考文本",
            "emotion_reference_audio": "E:/AiModel/tts/emotion.wav",
            "emo_alpha": 1.2,
            "extra": {"temperature": 0.8},
        },
        output={"format": "wav", "sample_rate": 22050},
    )

    synthesize_request = adapter.build_synthesize_request_from_generate(generate_request)
    mapped = adapter.build_request(synthesize_request)

    assert mapped.json["text"] == "你好"
    assert mapped.json["voice_id"] == "index-default"
    assert mapped.json["parameters"]["reference_audio"] == "E:/AiModel/tts/speaker.wav"
    assert mapped.json["parameters"]["reference_text"] == "主参考文本"
    assert mapped.json["parameters"]["extra"]["emotion_reference_audio"] == "E:/AiModel/tts/emotion.wav"
    assert mapped.json["parameters"]["extra"]["emo_alpha"] == 1.2
    assert mapped.json["parameters"]["extra"]["temperature"] == 0.8
