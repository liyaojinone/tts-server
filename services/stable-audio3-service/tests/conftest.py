from pathlib import Path
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ROOT = SERVICE_ROOT.parents[1]

for path in [
    SERVICE_ROOT,
    ROOT / "bobogen-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
