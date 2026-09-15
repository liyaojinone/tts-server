import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_portable_python_manifest_pins_the_windows_cp311_runtime():
    manifest_path = ROOT / "runtime" / "python" / "cp311" / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["python_version"].startswith("3.11.")
    assert manifest["target_triple"] == "x86_64-pc-windows-msvc"
    assert manifest["python_executable"] == "python.exe"
    assert manifest["archive_url"].endswith("install_only_stripped.tar.gz")
    assert len(manifest["archive_sha256"]) == 64
    int(manifest["archive_sha256"], 16)


def test_portable_python_installer_checks_the_pinned_manifest_before_extracting():
    installer = (ROOT / "scripts" / "install-portable-python.ps1").read_text(encoding="utf-8")

    assert "manifest.json" in installer
    assert "Get-FileHash" in installer
    assert "SHA256" in installer
    assert "tar.exe" in installer
    assert "curl.exe" in installer
    assert "--fail" in installer
    assert "--location" in installer


def test_portable_python_installer_allows_the_manifest_only_runtime_directory():
    installer = (ROOT / "scripts" / "install-portable-python.ps1").read_text(encoding="utf-8")

    assert 'Where-Object { $_.FullName -ne $manifestPath }' in installer
