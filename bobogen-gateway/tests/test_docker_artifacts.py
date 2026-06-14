from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_gateway_and_stable_audio3_profile():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))

    services = compose["services"]
    assert "gateway" in services
    assert "stable-audio3" in services
    assert "profiles" not in services["gateway"]
    assert services["stable-audio3"]["profiles"] == ["stable-audio3"]
    devices = services["stable-audio3"]["deploy"]["resources"]["reservations"]["devices"]
    assert devices == [{"driver": "nvidia", "count": "all", "capabilities": ["gpu"]}]
    assert services["gateway"]["environment"]["BOBOGEN_DEPLOYMENT"] == "docker"


def test_dockerfiles_and_dockerignore_keep_weights_out_of_images():
    gateway_dockerfile = (ROOT / "docker" / "gateway.Dockerfile").read_text(encoding="utf-8")
    stable_audio_dockerfile = (ROOT / "docker" / "stable-audio3.Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "python:3.11-slim" in gateway_dockerfile
    assert '"uvicorn"' in gateway_dockerfile
    assert '"app.main:create_app"' in gateway_dockerfile
    assert "nvidia/cuda" in stable_audio_dockerfile
    assert "Stability-AI/stable-audio-3" in stable_audio_dockerfile
    assert "models/**" in dockerignore
    assert ".git" in dockerignore
