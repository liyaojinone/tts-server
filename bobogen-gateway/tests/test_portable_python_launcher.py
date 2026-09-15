from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


def test_configure_import_paths_uses_explicit_directories_without_processing_pth(tmp_path, monkeypatch):
    from portable_python_launcher import configure_import_paths

    packages = tmp_path / "services" / "example-service" / ".venv" / "Lib" / "site-packages"
    source = tmp_path / "services" / "example-service"
    stale_editable_source = tmp_path.parent / "old-machine-source"
    packages.mkdir(parents=True)
    source.mkdir(exist_ok=True)
    stale_editable_source.mkdir()
    (packages / "__editable__.example.pth").write_text(str(stale_editable_source), encoding="utf-8")
    monkeypatch.setattr(sys, "path", list(sys.path))

    configure_import_paths(tmp_path, package_directories=[packages], source_directories=[source])

    assert sys.path[:2] == [str(source.resolve()), str(packages.resolve())]
    assert str(stale_editable_source.resolve()) not in sys.path


def test_launcher_runs_a_module_after_configuring_repository_local_imports(tmp_path, monkeypatch):
    from portable_python_launcher import main

    packages = tmp_path / "services" / "example-service" / ".venv" / "Lib" / "site-packages"
    output_path = tmp_path / "module-ran.txt"
    packages.mkdir(parents=True)
    (packages / "portable_probe.py").write_text(
        "from pathlib import Path\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "Path(os.environ['PORTABLE_PROBE_OUTPUT']).write_text(json.dumps(sys.argv), encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PORTABLE_PROBE_OUTPUT", str(output_path))
    monkeypatch.setattr(sys, "path", list(sys.path))

    assert main(
        [
            "--repo-root",
            str(tmp_path),
            "--packages",
            str(packages),
            "--module",
            "portable_probe",
            "--",
            "first-argument",
            "--option",
        ]
    ) == 0
    assert output_path.read_text(encoding="utf-8") == '["portable_probe", "first-argument", "--option"]'
