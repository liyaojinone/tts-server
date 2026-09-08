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
    assert "index_tts_2/v1/providers/status" not in start_script


def test_start_scripts_stop_stable_audio3_native_providers():
    linux_start_script = (ROOT / "start.sh").read_text(encoding="utf-8")
    windows_start_script = (ROOT / "start.ps1").read_text(encoding="utf-8")

    for provider_id in ["stable_audio_3_small_sfx", "stable_audio_3_small_music", "stable_audio_3_medium"]:
        assert provider_id in linux_start_script
        assert provider_id in windows_start_script


def test_start_scripts_stop_tiger_dnr_native_provider():
    linux_start_script = (ROOT / "start.sh").read_text(encoding="utf-8")
    windows_start_script = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "tiger_dnr" in linux_start_script
    assert "tiger_dnr" in windows_start_script


def test_qwen3_asr_uses_official_repo_working_directory_and_native_model_id():
    service_script = (ROOT / "services" / "qwen3-asr-service" / "start.ps1").read_text(
        encoding="utf-8"
    )
    provider_config = (
        ROOT / "bobogen-gateway" / "configs" / "providers" / "qwen3-asr-0_6b-windows.yaml"
    ).read_text(encoding="utf-8")

    assert "Set-Location $repoDir" in service_script


def test_windows_start_script_uses_single_gateway_log_file():
    start_script = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "gateway.log" in start_script
    assert "gateway.out.log" not in start_script
    assert "gateway.err.log" not in start_script
    assert "2>&1" in start_script


def test_windows_start_script_help_does_not_start_gateway_or_change_caller_directory():
    start_script = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "[switch]$Help" in start_script
    assert "function Show-Usage" in start_script
    assert "if ($Help)" in start_script
    assert "Push-Location $root" in start_script
    assert "Push-Location $gatewayDir" in start_script
    assert "finally {" in start_script
    assert start_script.count("Pop-Location") >= 2
    assert "Set-Location $root" not in start_script
    assert "Set-Location $gatewayDir" not in start_script
