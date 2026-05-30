from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for path in [
    ROOT / "local-tts-service-kit" / "src",
    ROOT / "local-tts-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
