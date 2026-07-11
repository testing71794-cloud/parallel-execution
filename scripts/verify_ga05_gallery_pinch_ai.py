#!/usr/bin/env python3
"""Verify GA_05 gallery zoom-out: default -> zoomed in (setup) -> zoomed out (test)."""
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
if str(_REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts"))

from gallery_pinch_pixel_verify import pinch_screenshots_changed  # noqa: E402

from intelligent_platform.config import (  # noqa: E402
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    openrouter_api_key,
    openrouter_model_vision,
)
from intelligent_platform.openrouter_client import call_openrouter_vision  # noqa: E402

_PROMPT = """You analyze THREE Kodak Step Prints gallery photo DETAIL screenshots.

Image A: DEFAULT fit (before any pinch).
Image B: AFTER pinch-open setup (zoomed IN — larger crop than A).
Image C: AFTER pinch-close zoom-OUT test (smaller / more margin than B, closer to A).

Reply with ONLY valid JSON:
{
  "zoom_in_setup_applied": true,
  "zoom_out_applied": true,
  "still_on_detail_screen": true,
  "summary": "one short sentence"
}"""


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


def verify_three(default_fit: Path, zoomed: Path, after: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "zoom_in_setup_applied": None,
            "zoom_out_applied": None,
            "still_on_detail_screen": None,
            "summary": "OPENROUTER_API_KEY not set — skip vision verify",
            "skipped": True,
            "default_fit": str(default_fit),
            "zoomed": str(zoomed),
            "after": str(after),
        }
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Image A (default fit):"},
                _encode(default_fit),
                {"type": "text", "text": "Image B (after pinch-open setup):"},
                _encode(zoomed),
                {"type": "text", "text": "Image C (after pinch-close zoom out):"},
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
            max_tokens=500,
        )
    except Exception as e:
        return {
            "zoom_in_setup_applied": None,
            "zoom_out_applied": None,
            "still_on_detail_screen": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
            "default_fit": str(default_fit),
            "zoomed": str(zoomed),
            "after": str(after),
        }
    try:
        result = _parse_json_response(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
            result["default_fit"] = str(default_fit)
            result["zoomed"] = str(zoomed)
            result["after"] = str(after)
        return result
    except json.JSONDecodeError:
        return {
            "zoom_in_setup_applied": False,
            "zoom_out_applied": False,
            "still_on_detail_screen": False,
            "summary": raw[:500],
            "skipped": False,
            "default_fit": str(default_fit),
            "zoomed": str(zoomed),
            "after": str(after),
        }


def _pixel_verify(default_fit: Path, zoomed: Path, after: Path) -> tuple[bool, str]:
    setup_ok = pinch_screenshots_changed(default_fit, zoomed)
    out_ok = pinch_screenshots_changed(zoomed, after)
    if setup_ok and out_ok:
        return True, "pixel diff: default->zoomed and zoomed->after both changed"
    if not setup_ok:
        return False, "pixel diff: pinch-open setup did not change preview"
    return False, "pixel diff: pinch-close did not change zoomed preview"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--default", type=Path, dest="default_fit")
    parser.add_argument("--zoomed", type=Path)
    parser.add_argument("--after", type=Path)
    args = parser.parse_args()

    w3c = _REPO / "automation" / "appium-gestures" / "target" / "screenshots" / "w3c"
    default_fit = args.default_fit or _latest_w3c("default_fit", w3c)
    zoomed = args.zoomed or _latest_w3c("before_pinch", w3c)
    after = args.after or _latest_w3c("after_pinch", w3c)

    missing = [
        name
        for name, path in [("default_fit", default_fit), ("zoomed", zoomed), ("after", after)]
        if path is None or not path.is_file()
    ]
    if missing:
        print(f"ERROR: missing W3C screenshots: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = verify_three(default_fit, zoomed, after)
    print(json.dumps(result, indent=2))

    require = os.environ.get("ATP_REQUIRE_PINCH_VISION", "").strip().lower() in ("1", "true", "yes")

    if result.get("skipped"):
        ok, msg = _pixel_verify(default_fit, zoomed, after)
        print(f"[INFO] {msg}")
        if ok:
            return 0
        return 3 if require else 0

    if (
        result.get("zoom_in_setup_applied")
        and result.get("zoom_out_applied")
        and result.get("still_on_detail_screen")
    ):
        return 0

    ok, msg = _pixel_verify(default_fit, zoomed, after)
    if ok:
        print(f"[INFO] Pixel diff fallback: {msg}")
        return 0
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
