#!/usr/bin/env python3
"""Build a Maestro wrapper flow that auto-records screen video around an ATP flow."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_wrapper(app_id: str, target_flow: Path, out_path: Path) -> None:
    flow_posix = target_flow.resolve().as_posix()
    # Maestro runFlow file: use forward slashes; quote for YAML double-quoted string.
    flow_yaml = flow_posix.replace("\\", "/").replace('"', '\\"')
    body = f"""appId: {app_id}
---
# Auto-generated ATP recording wrapper (startRecording/stopRecording around target flow).
- startRecording:
    path: recording
    optional: true
- runFlow:
    file: "{flow_yaml}"
- stopRecording
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_id")
    parser.add_argument("target_flow")
    parser.add_argument("wrapper_out")
    args = parser.parse_args()
    build_wrapper(args.app_id, Path(args.target_flow), Path(args.wrapper_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
