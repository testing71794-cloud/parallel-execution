"""Print one line: friendly device name for a serial (used from .bat for loops)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from utils.device_utils import get_device_name  # noqa: E402

if __name__ == "__main__":
    print(get_device_name(sys.argv[1] if len(sys.argv) > 1 else ""))
