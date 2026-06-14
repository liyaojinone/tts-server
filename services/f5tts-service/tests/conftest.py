from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
for path in [
    ROOT / "services" / "f5tts-service",
    ROOT / "bobogen-service-kit" / "src",
    ROOT / "bobogen-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
