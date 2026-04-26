#!/usr/bin/env python3
"""
Entry point for Jenkins / CLI: per-flow fan-out to all devices (default).

Delegates to execution.run_parallel_devices:main (same args as run_parallel_devices.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.run_parallel_devices import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
