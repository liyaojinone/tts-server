"""Bootstrap a service with repository-local dependency and source paths.

The launcher deliberately uses ``sys.path`` rather than ``site.addsitedir``.
The latter processes ``.pth`` files, including editable-install records that
contain the absolute source paths of the machine that created a venv.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import sys


def configure_import_paths(
    repo_root: Path,
    *,
    package_directories: Iterable[Path],
    source_directories: Iterable[Path],
) -> None:
    """Prepend explicit repository-local source and package directories."""

    root = repo_root.resolve()
    directories = [*source_directories, *package_directories]
    resolved_directories = [_repository_directory(root, directory) for directory in directories]

    for directory in reversed(resolved_directories):
        sys.path.insert(0, str(directory))


def _repository_directory(repo_root: Path, directory: Path) -> Path:
    resolved = directory.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"依赖路径必须位于 BoboGenServer 目录内: {directory}") from exc
    if not resolved.is_dir():
        raise ValueError(f"依赖目录不存在: {resolved}")
    return resolved
