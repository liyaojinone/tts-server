import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "services" / "index-tts-service"

for path in [
    SERVICE_ROOT,
    ROOT / "bobogen-protocol" / "src",
    ROOT / "bobogen-service-kit" / "src",
]:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
