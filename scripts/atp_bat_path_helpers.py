#!/usr/bin/env python3
"""CLI helpers for run_one_flow_on_device.bat (safe with spaces/parentheses in paths)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: atp_bat_path_helpers.py <safe_flow_stem|resolve_appium_runner> ...", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "safe_flow_stem":
        from execution.atp_folder_paths import safe_flow_stem

        print(safe_flow_stem(Path(sys.argv[2]).stem), end="")
        return 0
    if cmd == "resolve_appium_runner":
        from execution.flow_appium_runners import resolve_appium_runner_bat

        flow = Path(sys.argv[2])
        repo = Path(sys.argv[3])
        bat = resolve_appium_runner_bat(flow, repo)
        print(bat if bat else "", end="")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
