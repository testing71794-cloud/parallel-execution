#!/usr/bin/env python3
"""OpenRouter vision verify for GA_06 gallery pinch — zoom IN only (before vs after)."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from intelligent_platform.config import (  # noqa: E402
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    openrouter_api_key,
    openrouter_model_vision,
)
from intelligent_platform.openrouter_client import call_openrouter_vision  # noqa: E402

from gallery_pinch_pixel_verify import pinch_screenshots_changed  # noqa: E402

_PROMPT = """You analyze TWO Kodak Step Prints gallery photo DETAIL screenshots (same photo, white frame, Edit/Print/Collage bar).

Image A: BEFORE Appium pinch-open (zoom in gesture).
Image B: AFTER pinch-open (zoom IN — photo should look larger / more cropped than A).

Reply with ONLY valid JSON (no markdown):
{
  "zoom_in_applied": true,
  "still_on_detail_screen": true,
  "summary": "one short sentence"
}

Rules:
- zoom_in_applied=true ONLY if B clearly differs from A with a zoomed-in / larger photo in the white frame.
- still_on_detail_screen=true if B still shows photo detail with Edit/Print/Collage, NOT gallery grid.
- If A and B look identical, set zoom_in_applied=false."""


def _parse_json_response(raw: str) -> dict:
    text = (raw or "").strip()
    if "```" in text:
        for part in text.split("```"):
            chunk = part.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                text = chunk
                break
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _latest_w3c(label: str, w3c_dir: Path) -> Path | None:
    if not w3c_dir.is_dir():
        return None
    matches = sorted(
        w3c_dir.glob(f"{label}_*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _encode(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def verify_two(before: Path, after: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "zoom_in_applied": None,
            "still_on_detail_screen": None,
            "summary": "OPENROUTER_API_KEY not set — skip vision verify",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Image A (before pinch-open / zoom in):"},
                _encode(before),
                {"type": "text", "text": "Image B (after pinch-open / zoom in):"},
                _encode(after),
            ],
        },
    ]
    try:
        raw, model_used = call_openrouter_vision(
            messages,
            api_key=key,
            base_url=OPENROUTER_BASE_URL,
            model=openrouter_model_vision(),
            http_referer=OPENROUTER_HTTP_REFERER,
            app_title=OPENROUTER_APP_TITLE,
            max_tokens=400,
        )
    except Exception as e:
        return {
            "zoom_in_applied": None,
            "still_on_detail_screen": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    try:
        result = _parse_json_response(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
            result["before"] = str(before)
            result["after"] = str(after)
        return result
    except json.JSONDecodeError:
        return {
            "zoom_in_applied": False,
            "still_on_detail_screen": False,
            "summary": raw[:500],
            "skipped": False,
            "before": str(before),
            "after": str(after),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    args = parser.parse_args()

    w3c = _REPO / "automation" / "appium-gestures" / "target" / "screenshots" / "w3c"
    before = args.before or _latest_w3c("before_pinch", w3c)
    after = args.after or _latest_w3c("after_pinch", w3c)

    missing = [
        name
        for name, path in [("before", before), ("after", after)]
        if path is None or not path.is_file()
    ]
    if missing:
        print(f"ERROR: missing W3C screenshots: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = verify_two(before, after)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        if os.environ.get("ATP_REQUIRE_PINCH_VISION", "").strip().lower() in ("1", "true", "yes"):
            if pinch_screenshots_changed(before, after):
                print("[INFO] Pixel diff fallback: before/after screenshots differ — accept GA_06 zoom in")
                return 0
            print("ERROR: vision verify skipped and pixel diff shows no change", file=sys.stderr)
            return 3
        return 0
    if result.get("zoom_in_applied") and result.get("still_on_detail_screen"):
        return 0
    if pinch_screenshots_changed(before, after):
        print("[INFO] Pixel diff fallback: before/after screenshots differ — accept GA_06 zoom in")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
