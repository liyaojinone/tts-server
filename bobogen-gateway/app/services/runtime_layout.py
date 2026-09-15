"""Repository-local paths used by the portable Python runtime."""

from __future__ import annotations

from pathlib import Path


class PortableRuntimeLayout:
    """Resolve the single CPython runtime and isolated service package paths.

    Existing ``.venv`` directories remain the source of package files during the
    first migration stage.  Their Windows launchers are deliberately not used:
    those launchers contain the absolute path of the Python installation that
    created them.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    @property
    def python_executable(self) -> Path:
        return self._repository_path("runtime/python/cp311/python.exe")

    @property
    def gateway_packages(self) -> Path:
        return self._repository_path("runtime/gateway/.venv/Lib/site-packages")

    def service_packages(self, service_root: str | Path) -> Path:
        service_path = self._repository_path(service_root, "服务根目录必须位于 BoboGenServer 目录内")
        relative_service_path = service_path.relative_to(self.repo_root)
        if len(relative_service_path.parts) < 2 or relative_service_path.parts[0] != "services":
            raise ValueError("服务根目录必须位于 services 目录内")
        return self._repository_path(
            relative_service_path / ".venv/Lib/site-packages",
            "服务根目录必须位于 BoboGenServer 目录内",
        )

    def _repository_path(self, relative_path: str | Path, error_message: str | None = None) -> Path:
        candidate = (self.repo_root / relative_path).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError(error_message or "路径必须位于 BoboGenServer 目录内") from exc
        return candidate
