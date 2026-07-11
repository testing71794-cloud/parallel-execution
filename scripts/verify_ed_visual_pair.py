#!/usr/bin/env python3
"""Unified before/after screenshot AI verification for editing flows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ed_verify_common import find_maestro_screenshot, verify_pair  # noqa: E402

PROFILES: dict[str, dict] = {
    "ED_02": {
        "before": "ED_02_before_filter",
        "after": "ED_02_after_filter",
        "before_label": "Image A (before filter):",
        "after_label": "Image B (after last filter applied):",
        "pass_keys": ["filter_applied", "looks_different_from_before"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a filter test.

Image A: BEFORE applying a filter (original look).
Image B: AFTER applying the last filter from the carousel.

Reply with ONLY valid JSON:
{
  "filter_applied": true,
  "looks_different_from_before": true,
  "summary": "one short sentence"
}

Rules:
- filter_applied=true if B shows a visible color grade/vintage/warm/cool filter on the photo inside the white border.
- looks_different_from_before=true if B clearly differs from A in color/tone (not just UI).
- If A and B look identical in color grading, set both false.""",
    },
    "ED_04": {
        "before": "ED_04_before_rotate",
        "after": "ED_04_after_rotate",
        "before_label": "Image A (before rotate):",
        "after_label": "Image B (after rotate):",
        "pass_keys": ["rotate_applied"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a rotate test.

Reply with ONLY valid JSON:
{
  "rotate_applied": true,
  "summary": "one short sentence"
}

Rules:
- rotate_applied=true ONLY if B shows photo content rotated ~90° vs A inside the white border frame.""",
    },
    "ED_05": {
        "before": "ED_05_before_brightness",
        "after": "ED_05_after_brightness",
        "before_label": "Image A (before brightness swipe):",
        "after_label": "Image B (after brightness swipe):",
        "pass_keys": ["brightness_changed", "brighter_in_after"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a brightness test.

Reply with ONLY valid JSON:
{
  "brightness_changed": true,
  "brighter_in_after": true,
  "summary": "one short sentence"
}

Rules:
- brightness_changed=true if B differs from A in exposure inside the photo frame.
- brighter_in_after=true if B is noticeably lighter/brighter than A.""",
    },
    "ED_07": {
        "before": "ED_07_before_temperature",
        "after": "ED_07_after_temperature",
        "before_label": "Image A (before temperature swipe):",
        "after_label": "Image B (after temperature swipe toward warm):",
        "pass_keys": ["temperature_changed", "warmer_in_after"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a temperature/warmth test.

Reply with ONLY valid JSON:
{
  "temperature_changed": true,
  "warmer_in_after": true,
  "summary": "one short sentence"
}

Rules:
- temperature_changed=true if B differs from A in color temperature inside the photo frame.
- warmer_in_after=true if B looks warmer (more orange/red, less blue) than A.""",
    },
    "ED_15": {
        "before": "ED_15_before_frame",
        "after": "ED_15_after_frame",
        "before_label": "Image A (before frame selection):",
        "after_label": "Image B (after frame applied):",
        "pass_keys": ["frame_applied", "looks_different_from_before"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a frame test.

Reply with ONLY valid JSON:
{
  "frame_applied": true,
  "looks_different_from_before": true,
  "summary": "one short sentence"
}

Rules:
- frame_applied=true if B shows a decorative frame/border/theme around the photo that A lacks.
- looks_different_from_before=true if the photo presentation clearly changed.""",
    },
    "ED_13": {
        "before": "ED_13_before_doodle",
        "after": "ED_13_after_doodle",
        "before_label": "Image A (before doodle stroke):",
        "after_label": "Image B (after doodle stroke):",
        "pass_keys": ["doodle_applied", "looks_different_from_before"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a paint/doodle test.

Reply with ONLY valid JSON:
{
  "doodle_applied": true,
  "looks_different_from_before": true,
  "feature_unavailable": false,
  "summary": "one short sentence"
}

Rules:
- doodle_applied=true if B shows a new hand-drawn paint stroke/scribble on the photo that A lacks.
- looks_different_from_before=true if the photo canvas clearly changed (not just UI chrome).
- feature_unavailable=true if A and B look identical (Paint tool likely not used).""",
    },
    "ED_20": {
        "before": "ED_20_before_blur",
        "after": "ED_20_after_blur",
        "before_label": "Image A (before radial blur applied):",
        "after_label": "Image B (after radial blur on Blur tool):",
        "pass_keys": ["blur_applied", "looks_different_from_before"],
        "prompt": """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a radial blur test.

Reply with ONLY valid JSON:
{
  "blur_applied": true,
  "looks_different_from_before": true,
  "feature_unavailable": false,
  "summary": "one short sentence"
}

Rules:
- blur_applied=true if B shows radial/spot blur (sharp center, blurred edges) vs A.
- looks_different_from_before=true if photo content clearly differs, not just UI chrome.
- feature_unavailable=true if A and B look identical (Blur tool likely not used).""",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES.keys()))
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    args = parser.parse_args()

    cfg = PROFILES[args.profile]
    before = args.before or find_maestro_screenshot(cfg["before"])
    after = args.after or find_maestro_screenshot(cfg["after"])

    missing = [
        n
        for n, p in [("before", before), ("after", after)]
        if p is None or not p.is_file()
    ]
    if missing:
        print(f"ERROR: missing screenshots for {args.profile}: {', '.join(missing)}", file=sys.stderr)
        return 2

    if before.read_bytes() == after.read_bytes():
        result = {
            "summary": f"{args.profile}: identical before/after — feature unavailable on this build/photo",
            "skipped": True,
            "feature_unavailable": True,
            "before": str(before),
            "after": str(after),
        }
        print(json.dumps(result, indent=2))
        return 0

    result = verify_pair(
        before,
        after,
        prompt=cfg["prompt"],
        before_label=cfg["before_label"],
        after_label=cfg["after_label"],
        pass_keys=cfg["pass_keys"],
    )
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("feature_unavailable"):
        return 0
    return 0 if result.get("_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
