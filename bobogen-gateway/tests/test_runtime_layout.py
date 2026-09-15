from pathlib import Path

import pytest


def test_portable_runtime_layout_uses_one_repository_local_python(tmp_path: Path):
    from app.services.runtime_layout import PortableRuntimeLayout

    layout = PortableRuntimeLayout(tmp_path)

    assert layout.python_executable == tmp_path / "runtime" / "python" / "cp311" / "python.exe"
    assert layout.gateway_packages == tmp_path / "runtime" / "gateway" / ".venv" / "Lib" / "site-packages"
    assert layout.service_packages("services/cosyvoice-service") == (
        tmp_path / "services" / "cosyvoice-service" / ".venv" / "Lib" / "site-packages"
    )


def test_portable_runtime_layout_rejects_paths_outside_repository(tmp_path: Path):
    from app.services.runtime_layout import PortableRuntimeLayout

    layout = PortableRuntimeLayout(tmp_path)

    with pytest.raises(ValueError, match="服务根目录必须位于 BoboGenServer 目录内"):
        layout.service_packages("../outside-service")


def test_portable_runtime_layout_accepts_only_service_directories(tmp_path: Path):
    from app.services.runtime_layout import PortableRuntimeLayout

    layout = PortableRuntimeLayout(tmp_path)

    with pytest.raises(ValueError, match="服务根目录必须位于 services 目录内"):
        layout.service_packages("runtime/gateway")
