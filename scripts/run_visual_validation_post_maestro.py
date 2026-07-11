#!/usr/bin/env python3
"""
Opt-in post-Maestro AI visual validation hook.

Does NOT modify Maestro YAML, Jenkins stages, or run_one_flow_on_device.bat.
Invoke manually or from CI via a separate step after Maestro completes:

  py -3 scripts/run_visual_validation_post_maestro.py --status-file status/editing__ED_Q1__DEVICE.txt

Always exits 0 so Jenkins / Maestro status is never affected.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_AI_DIR = _REPO / "ai"
if str(_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_DIR))

import visual_validation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post-Maestro Qwen3 VL visual validation (opt-in)")
    parser.add_argument("--status-file", type=Path, help="status/*.txt written by run_one_flow_on_device.bat")
    parser.add_argument("--artifact-dir", type=Path, help="Maestro test-output / debug directory")
    parser.add_argument("--screenshot", type=Path, help="Single screenshot PNG")
    parser.add_argument("--expected", type=Path, help="Expected PNG for compare mode")
    parser.add_argument("--testcase-id", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--mode", choices=["single", "compare"], default="single")
    parser.add_argument("--config", type=Path, help="Path to ai/config.yaml")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    try:
        visual_validation.run_post_maestro(
            status_file=args.status_file,
            artifact_dir=args.artifact_dir,
            screenshot=args.screenshot,
            expected=args.expected,
            testcase_id=args.testcase_id,
            context=args.context,
            mode=visual_validation.ValidationMode.COMPARE
            if args.mode == "compare" or args.expected
            else visual_validation.ValidationMode.SINGLE,
            config_path=args.config,
            verbose=args.verbose,
        )
    except Exception as exc:
        # Never fail the pipeline — log and continue
        print(f"[visual_validation] skipped due to error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
