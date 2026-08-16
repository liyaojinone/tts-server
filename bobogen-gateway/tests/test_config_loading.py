from pathlib import Path

import pytest


def test_load_provider_configs():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"

    providers = load_provider_configs(config_dir)

    provider_ids = {provider.provider_id for provider in providers}
    provider_types = {provider.provider_type for provider in providers}

    assert provider_ids == {
        "cosyvoice2",
        "f5_tts",
        "gpt_sovits_v2pro",
        "index_tts_2",
        "campplus_speaker_diarization",
        "qwen3_forced_aligner_0_6b",
        "qwen3_asr_0_6b",
        "qwen3_asr_1_7b",
        "stable_audio_3_medium",
        "stable_audio_3_small_music",
        "stable_audio_3_small_sfx",
        "tiger_dnr",
        "voxcpm2",
    }
    assert provider_types == {
        "cosyvoice",
        "f5-tts",
        "gptsovits",
        "indextts",
        "qwen3-asr",
        "speaker-diarization",
        "stableaudio3",
        "tiger-dnr",
        "voxcpm",
    }
    assert {provider.runtime.launch_mode for provider in providers} == {"process"}


def test_target_providers_launch_repository_local_services():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"

    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    expected = {
        "cosyvoice2": ("cosyvoice-service", "COSYVOICE_REPO_DIR", r"models\cosyvoice\repo"),
        "f5_tts": ("f5tts-service", "F5TTS_REPO_DIR", r"models\f5-tts\repo"),
        "gpt_sovits_v2pro": ("gptsovits-service", "GPTSOVITS_REPO_DIR", r"models\gpt-sovits\repo"),
    }
    for provider_id, (service_dir, repo_env, repo_suffix) in expected.items():
        provider = providers[provider_id]
        command = provider.runtime.command

        assert provider.runtime.root_dir.endswith(rf"services\{service_dir}")
        assert provider.runtime.cwd.endswith(rf"services\{service_dir}")
        assert command[:2] == ["powershell", "-File"]
        assert command[2].endswith(rf"services\{service_dir}\start.ps1")
        assert provider.runtime.env[repo_env].endswith(repo_suffix)
        assert provider.network.healthcheck_path == "/v1/health"
        assert provider.capabilities.clone is True


def test_stable_audio3_provider_launches_repository_local_service():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    provider = providers["stable_audio_3_small_sfx"]

    assert provider.model_id == "stable_audio_3_small_sfx"
    assert provider.provider_type == "stableaudio3"
    assert provider.tasks == ["audio.generate"]
    assert provider.runtime.root_dir.endswith(r"services\stable-audio3-service")
    assert provider.runtime.cwd.endswith(r"services\stable-audio3-service")
    assert provider.runtime.command[:2] == ["powershell", "-File"]
    assert provider.runtime.command[2].endswith(r"services\stable-audio3-service\start.ps1")
    assert provider.runtime.env["STABLE_AUDIO3_REPO_DIR"].endswith(r"models\stable-audio-3\repo")
    assert provider.network.healthcheck_path == "/v1/health"
    assert provider.capabilities.synthesize is False


def test_stable_audio3_medium_provider_launches_on_separate_port():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    provider = providers["stable_audio_3_medium"]

    assert provider.model_id == "stable_audio_3_medium"
    assert provider.provider_type == "stableaudio3"
    assert provider.tasks == ["audio.generate"]
    assert provider.runtime.env["STABLE_AUDIO3_MODEL_ID"] == "stable_audio_3_medium"
    assert provider.runtime.env["STABLE_AUDIO3_MODEL_NAME"] == "medium"
    assert provider.runtime.env["STABLE_AUDIO3_HF_REPO_ID"] == "stabilityai/stable-audio-3-medium"
    assert provider.runtime.env["STABLE_AUDIO3_MODEL_DIR"].endswith(
        r"models\stable-audio-3\modelscope\stable-audio-3-medium"
    )
    assert provider.runtime.env["STABLE_AUDIO3_PORT"] == "5107"
    assert provider.network.port == 5107
    assert provider.network.base_url == "http://127.0.0.1:5107"


def test_stable_audio3_small_music_provider_launches_on_separate_port():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    provider = providers["stable_audio_3_small_music"]

    assert provider.model_id == "stable_audio_3_small_music"
    assert provider.provider_type == "stableaudio3"
    assert provider.tasks == ["audio.generate"]
    assert provider.runtime.env["STABLE_AUDIO3_MODEL_ID"] == "stable_audio_3_small_music"
    assert provider.runtime.env["STABLE_AUDIO3_MODEL_NAME"] == "small-music"
    assert provider.runtime.env["STABLE_AUDIO3_HF_REPO_ID"] == "stabilityai/stable-audio-3-small-music"
    assert provider.runtime.env["STABLE_AUDIO3_PORT"] == "5108"
    assert provider.network.port == 5108
    assert provider.network.base_url == "http://127.0.0.1:5108"


def test_qwen3_asr_providers_launch_gpu_service_on_separate_ports():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    small = providers["qwen3_asr_0_6b"]
    large = providers["qwen3_asr_1_7b"]

    assert small.model_id == "qwen3_asr_0_6b"
    assert small.provider_type == "qwen3-asr"
    assert small.tasks == ["asr.transcribe"]
    assert small.runtime.root_dir.endswith(r"services\qwen3-asr-service")
    assert small.runtime.command[:2] == ["powershell", "-File"]
    assert small.runtime.command[2].endswith(r"services\qwen3-asr-service\start.ps1")
    assert small.runtime.env["QWEN3_ASR_HF_REPO_ID"] == "Qwen/Qwen3-ASR-0.6B"
    assert small.runtime.env["QWEN3_ASR_DEVICE"] == "cuda:0"
    assert small.runtime.env["QWEN3_ASR_PORT"] == "5110"
    assert small.network.port == 5110
    assert small.network.base_url == "http://127.0.0.1:5110"
    assert small.capabilities.synthesize is False

    assert large.model_id == "qwen3_asr_1_7b"
    assert large.provider_type == "qwen3-asr"
    assert large.tasks == ["asr.transcribe"]
    assert large.runtime.env["QWEN3_ASR_HF_REPO_ID"] == "Qwen/Qwen3-ASR-1.7B"
    assert large.runtime.env["QWEN3_ASR_DEVICE"] == "cuda:0"
    assert large.runtime.env["QWEN3_ASR_PORT"] == "5111"
    assert large.network.port == 5111
    assert large.network.base_url == "http://127.0.0.1:5111"

    aligner = providers["qwen3_forced_aligner_0_6b"]
    assert aligner.model_id == "qwen3_forced_aligner_0_6b"
    assert aligner.provider_type == "qwen3-asr"
    assert aligner.tasks == ["audio.align"]
    assert (
        aligner.runtime.env["QWEN3_ASR_HF_REPO_ID"]
        == "Qwen/Qwen3-ForcedAligner-0.6B-hf"
    )
    assert aligner.runtime.env["QWEN3_ASR_MODEL_DIR"].endswith(
        r"models\qwen3-asr\Qwen3-ForcedAligner-0.6B-hf"
    )
    assert aligner.runtime.env["QWEN3_ASR_PYTHON"].endswith(
        r"services\qwen3-asr-service\.venv-aligner\Scripts\python.exe"
    )
    assert aligner.runtime.env["QWEN3_ASR_DEVICE"] == "cuda:0"
    assert aligner.runtime.env["QWEN3_ASR_PORT"] == "5112"
    assert aligner.network.port == 5112
    assert aligner.network.base_url == "http://127.0.0.1:5112"


def test_campplus_speaker_diarization_provider_launches_modelscope_service():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    provider = providers["campplus_speaker_diarization"]

    assert provider.model_id == "campplus_speaker_diarization"
    assert provider.provider_type == "speaker-diarization"
    assert provider.tasks == ["audio.diarize"]
    assert provider.runtime.root_dir.endswith(r"services\speaker-diarization-service")
    assert provider.runtime.cwd.endswith(r"services\speaker-diarization-service")
    assert provider.runtime.command[:2] == ["powershell", "-File"]
    assert provider.runtime.command[2].endswith(r"services\speaker-diarization-service\start.ps1")
    assert provider.runtime.env["SPEAKER_DIARIZATION_MODEL_ID"] == "campplus_speaker_diarization"
    assert provider.runtime.env["SPEAKER_DIARIZATION_MODEL_NAME"] == "iic/speech_campplus_speaker-diarization_common"
    assert provider.runtime.env["SPEAKER_DIARIZATION_MODEL_REVISION"] == "master"
    assert provider.runtime.env["SPEAKER_DIARIZATION_DEVICE"] == "cuda:0"
    assert provider.runtime.env["SPEAKER_DIARIZATION_PORT"] == "5113"
    assert provider.network.port == 5113
    assert provider.network.base_url == "http://127.0.0.1:5113"
    assert provider.capabilities.synthesize is False


def test_docker_deployment_loads_only_docker_provider_configs(monkeypatch):
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    monkeypatch.setenv("BOBOGEN_DEPLOYMENT", "docker")

    providers = load_provider_configs(config_dir)

    assert [provider.provider_id for provider in providers] == ["stable_audio_3_small_sfx"]
    provider = providers[0]
    assert provider.runtime.launch_mode == "external"
    assert provider.network.base_url == "http://stable-audio3:5106"
    assert provider.model_id == "stable_audio_3_small_sfx"
    assert provider.tasks == ["audio.generate"]


def test_linux_deployment_loads_stable_audio3_linux_provider(monkeypatch):
    import app.config as config

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    monkeypatch.delenv("BOBOGEN_DEPLOYMENT", raising=False)
    monkeypatch.setattr(config, "_IS_LINUX", True)
    monkeypatch.setattr(config, "_IS_WIN", False)

    providers = {provider.provider_id: provider for provider in config.load_provider_configs(config_dir)}
    provider = providers["stable_audio_3_small_sfx"]

    assert provider.runtime.launch_mode == "process"
    assert provider.runtime.command[0] == "bash"
    assert provider.runtime.command[1].replace("\\", "/").endswith("/services/stable-audio3-service/start.sh")
    assert provider.runtime.env["STABLE_AUDIO3_REPO_DIR"].replace("\\", "/").endswith("/models/stable-audio-3/repo")


def test_versioned_tts_provider_configs_use_distinct_ids_models_and_ports():
    from app.config import load_provider_configs

    config_dir = Path(__file__).resolve().parents[1] / "configs" / "providers"
    providers = {provider.provider_id: provider for provider in load_provider_configs(config_dir)}

    expected = {
        "cosyvoice2": ("cosyvoice2", "cosyvoice", 5101),
        "f5_tts": ("f5_tts", "f5-tts", 5102),
        "gpt_sovits_v2pro": ("gpt_sovits_v2pro", "gptsovits", 5103),
        "index_tts_2": ("index_tts_2", "indextts", 5104),
        "voxcpm2": ("voxcpm2", "voxcpm", 5105),
    }

    for provider_id, (model_id, provider_type, port) in expected.items():
        provider = providers[provider_id]
        assert provider.model_id == model_id
        assert provider.provider_type == provider_type
        assert provider.network.port == port
        assert provider.runtime.env

    gpt = providers["gpt_sovits_v2pro"]
    assert gpt.runtime.env["GPTSOVITS_MODEL_ID"] == "gpt_sovits_v2pro"
    assert gpt.runtime.env["GPTSOVITS_GPT_WEIGHTS_PATH"].endswith(r"gpt_sovits_v2pro\s1v3.ckpt")
    assert gpt.runtime.env["GPTSOVITS_SOVITS_WEIGHTS_PATH"].endswith(
        r"gpt_sovits_v2pro\v2Pro\s2Gv2Pro.pth"
    )
    assert gpt.runtime.env["GPTSOVITS_SV_WEIGHTS_PATH"].endswith(
        r"gpt_sovits_v2pro\sv\pretrained_eres2netv2w24s4ep4.ckpt"
    )
    assert gpt.runtime.env["GPTSOVITS_PROFILE_DIR"].endswith(r"profiles\gpt_sovits_v2pro")
    assert gpt.runtime.env["GPTSOVITS_OUTPUT_DIR"].endswith(r"outputs\gpt_sovits_v2pro")
    assert gpt.runtime.env["GPTSOVITS_HOST"] == gpt.network.host
    assert gpt.runtime.env["GPTSOVITS_PORT"] == "5103"

    voxcpm = providers["voxcpm2"]
    assert voxcpm.runtime.env["VOXCPM_MODEL_ID"] == "voxcpm2"
    assert voxcpm.runtime.env["VOXCPM_MODEL_WEIGHTS_PATH"].endswith(r"checkpoints\model.safetensors")
    assert voxcpm.runtime.env["VOXCPM_AUDIOVAE_WEIGHTS_PATH"].endswith(r"checkpoints\audiovae.pth")
    assert voxcpm.runtime.env["VOXCPM_EXPECTED_ARCHITECTURE"] == "voxcpm2"
    assert voxcpm.runtime.env["VOXCPM_PROFILE_DIR"].endswith(r"profiles\voxcpm2")
    assert voxcpm.runtime.env["VOXCPM_OUTPUT_DIR"].endswith(r"outputs\voxcpm2")
    assert voxcpm.runtime.env["VOXCPM_HOST"] == voxcpm.network.host
    assert voxcpm.runtime.env["VOXCPM_PORT"] == "5105"


def _write_provider_config(
    path: Path,
    provider_id: str,
    model_id: str,
    port: int,
    host: str = "127.0.0.1",
) -> None:
    path.write_text(
        f"""
provider_id: {provider_id}
model_id: {model_id}
provider_type: f5-tts
display_name: Test provider
runtime:
  root_dir: C:/service
  cwd: C:/service
  command: [python, -m, app.main]
network:
  host: {host}
  port: {port}
  base_url: http://{host}:{port}
capabilities: {{}}
""".lstrip(),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("second_provider_id", "second_model_id", "second_port", "second_host", "message"),
    [
        ("provider_one", "model_two", 5202, "127.0.0.1", "Duplicate provider_id"),
        ("provider_two", "model_one", 5202, "127.0.0.1", "Duplicate model_id"),
        ("provider_two", "model_two", 5201, "127.0.0.1", "Duplicate network endpoint"),
        ("provider_two", "model_two", 5201, "127.0.0.2", "Duplicate local process port"),
    ],
)
def test_load_provider_configs_rejects_duplicate_identity_or_endpoint(
    tmp_path,
    second_provider_id,
    second_model_id,
    second_port,
    second_host,
    message,
):
    from app.config import load_provider_configs

    _write_provider_config(tmp_path / "one.yaml", "provider_one", "model_one", 5201)
    _write_provider_config(
        tmp_path / "two.yaml",
        second_provider_id,
        second_model_id,
        second_port,
        second_host,
    )

    with pytest.raises(ValueError, match=message):
        load_provider_configs(tmp_path)
