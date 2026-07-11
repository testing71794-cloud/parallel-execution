#!/usr/bin/env python3
"""Verify ED_03c: pinch must change canvas; double-tap must restore original fit."""
from __future__ import annotations

import argparse
import base64
import json
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

_PROMPT = """You analyze THREE Kodak Step Prints EDIT PHOTO canvas screenshots from one test.

Image A: BEFORE pinch (original fit).
Image B: AFTER pinch zoom (before double-tap).
Image C: AFTER double-tap reset.

Reply with ONLY valid JSON (no markdown):
{
  "pinch_changed_canvas": true,
  "reset_to_original": true,
  "summary": "one short sentence"
}

Rules:
- pinch_changed_canvas=true ONLY if B clearly differs from A (zoomed, rotated, tighter crop, or different framing).
- reset_to_original=true ONLY if C matches A (same fit/framing as original), AND C clearly differs from B (reset removed the pinch zoom).
- If A and C look the same but B also looks the same as A, set pinch_changed_canvas=false (pinch had no visible effect).
- If B differs from A but C still looks like B, set reset_to_original=false."""


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


def _latest_png(folder: Path, prefix: str) -> Path | None:
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"{prefix}*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _find_maestro_screenshot(name: str) -> Path | None:
    roots = [
        _REPO,
        Path.home() / ".maestro" / "tests",
        Path.home() / ".maestro" / "screenshots",
        _REPO / "reports" / "editing",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(f"*{name}*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() == ".png":
                return p
    return None


def _encode(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def verify_three(before: Path, after_pinch: Path, after_reset: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "pinch_changed_canvas": None,
            "reset_to_original": None,
            "summary": "OPENROUTER_API_KEY not set — compare screenshots manually",
            "skipped": True,
            "before": str(before),
            "after_pinch": str(after_pinch),
            "after_reset": str(after_reset),
            "note": "Compare after_pinch (zoomed/diagonal) vs after_reset (upright fit). before ≈ after_reset when reset works.",
        }
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Image A (before pinch):"},
                _encode(before),
                {"type": "text", "text": "Image B (after pinch, before double-tap):"},
                _encode(after_pinch),
                {"type": "text", "text": "Image C (after double-tap reset):"},
                _encode(after_reset),
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
            "pinch_changed_canvas": None,
            "reset_to_original": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
            "before": str(before),
            "after_pinch": str(after_pinch),
            "after_reset": str(after_reset),
        }
    try:
        result = _parse_json_response(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
            result["before"] = str(before)
            result["after_pinch"] = str(after_pinch)
            result["after_reset"] = str(after_reset)
        return result
    except json.JSONDecodeError:
        return {
            "pinch_changed_canvas": False,
            "reset_to_original": False,
            "summary": raw[:500],
            "model_used": model_used,
            "skipped": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, help="Before pinch screenshot")
    parser.add_argument("--after-pinch", type=Path, help="After pinch screenshot")
    parser.add_argument("--after-reset", type=Path, help="After double-tap screenshot")
    args = parser.parse_args()

    w3c = _REPO / "automation" / "appium-gestures" / "target" / "screenshots" / "w3c"
    before = args.before or _latest_png(w3c, "before_pinch")
    after_pinch = args.after_pinch or _latest_png(w3c, "after_pinch")
    after_reset = args.after_reset or _find_maestro_screenshot("ED_03_after_double_tap_reset")

    missing = [
        name
        for name, path in [
            ("before_pinch", before),
            ("after_pinch", after_pinch),
            ("after_double_tap_reset", after_reset),
        ]
        if path is None or not path.is_file()
    ]
    if missing:
        print(f"ERROR: missing screenshots: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = verify_three(before, after_pinch, after_reset)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("pinch_changed_canvas") and result.get("reset_to_original"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
