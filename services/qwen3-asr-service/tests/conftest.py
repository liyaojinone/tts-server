from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
PROTOCOL_SRC = WORKSPACE_ROOT / "bobogen-protocol" / "src"

for path in (PROJECT_ROOT, PROTOCOL_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
