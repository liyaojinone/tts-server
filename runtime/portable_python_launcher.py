"""Bootstrap a service with repository-local dependency and source paths.

The launcher deliberately uses ``sys.path`` rather than ``site.addsitedir``.
The latter processes ``.pth`` files, including editable-install records that
contain the absolute source paths of the machine that created a venv.
"""

from __future__ import annotations

from collections.abc import Iterable
import argparse
from pathlib import Path
import runpy
import sys


PYWIN32_RUNTIME_DIRECTORIES = ("win32", "win32/lib", "pythonwin", "pywin32_system32")


def configure_import_paths(
    repo_root: Path,
    *,
    package_directories: Iterable[Path],
    source_directories: Iterable[Path],
) -> None:
    """Prepend explicit repository-local source and package directories."""

    root = repo_root.resolve()
    resolved_sources = [_repository_directory(root, directory) for directory in source_directories]
    resolved_packages = [_repository_directory(root, directory) for directory in package_directories]
    package_import_directories = [
        directory
        for package_directory in resolved_packages
        for directory in _package_import_directories(package_directory)
    ]
    resolved_directories = [*resolved_sources, *package_import_directories]

    for directory in reversed(resolved_directories):
        sys.path.insert(0, str(directory))


def _package_import_directories(package_directory: Path) -> list[Path]:
    directories = [package_directory]
    for relative_path in PYWIN32_RUNTIME_DIRECTORIES:
        candidate = package_directory / relative_path
        if candidate.is_dir():
            directories.append(candidate)
    return directories


def _repository_directory(repo_root: Path, directory: Path) -> Path:
    resolved = directory.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"依赖路径必须位于 BoboGenServer 目录内: {directory}") from exc
    if not resolved.is_dir():
        raise ValueError(f"依赖目录不存在: {resolved}")
    return resolved


def main(arguments: list[str] | None = None) -> int:
    """Configure imports, then execute the requested Python module."""

    parser = argparse.ArgumentParser(description="BoboGenServer portable Python launcher")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--packages", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--module", required=True)
    parser.add_argument("module_arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(arguments)

    configure_import_paths(
        Path(options.repo_root),
        package_directories=[Path(directory) for directory in options.packages],
        source_directories=[Path(directory) for directory in options.source],
    )
    module_arguments = options.module_arguments
    if module_arguments[:1] == ["--"]:
        module_arguments = module_arguments[1:]
    sys.argv = [options.module, *module_arguments]
    runpy.run_module(options.module, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
