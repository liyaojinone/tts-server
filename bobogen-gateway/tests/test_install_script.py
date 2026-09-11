from pathlib import Path


def test_gateway_installation_stops_when_pip_fails() -> None:
    source = (Path(__file__).resolve().parents[2] / "install.ps1").read_text(encoding="utf-8")

    assert "if ($LASTEXITCODE -ne 0)" in source
    assert "Gateway 依赖安装失败" in source


def test_gateway_package_declares_explicit_app_package_discovery() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.setuptools.packages.find]" in pyproject
    assert 'include = ["app*"]' in pyproject
