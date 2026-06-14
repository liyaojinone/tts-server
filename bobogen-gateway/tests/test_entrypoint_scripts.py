from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_install_script_offers_stable_audio3_native_install():
    install_script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "Stable Audio 3 Small-SFX" in install_script
    assert "stableaudio3" in install_script
    assert "https://github.com/Stability-AI/stable-audio-3.git" in install_script
    assert "huggingface-cli login" in install_script


def test_start_script_supports_native_and_docker_operations_without_provider_scope_hack():
    start_script = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "--docker" in start_script
    assert "--model" in start_script
    assert "docker compose --profile stable-audio3 up -d stable-audio3" in start_script
    assert "/v1/providers/status" in start_script
    assert "local_index_tts/v1/providers/status" not in start_script
