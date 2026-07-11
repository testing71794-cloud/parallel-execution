#!/usr/bin/env python3
"""OpenRouter vision verify for ED_03 photo detail pinch (video 29). Compare before/after detail preview."""
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

_PROMPT = """You analyze TWO Kodak Step Prints photo DETAIL preview screenshots (video 29 flow).

Image A: BEFORE two-finger pinch on photo detail (Edit/Print/Collage visible at bottom).
Image B: AFTER pinch on the same photo detail preview.

Reply with ONLY valid JSON (no markdown):
{
  "pinch_changed_preview": true,
  "still_on_detail_screen": true,
  "summary": "one short sentence"
}

Rules:
- pinch_changed_preview=true ONLY if B clearly differs from A (zoom, rotation, tighter crop, or different framing inside the white preview frame).
- still_on_detail_screen=true if B still looks like photo detail with action buttons (Edit, Print, Collage), NOT gallery grid or Edit Photo toolbar.
- If A and B look identical, set pinch_changed_preview=false."""


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


def _find_screenshot(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(f"*{name}*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                return p
    return None


def _encode(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def default_search_roots() -> list[Path]:
    return [
        _REPO,
        _REPO / "reports" / "editing",
        Path.home() / ".maestro" / "tests",
        Path.home() / ".maestro" / "screenshots",
        _REPO / "automation" / "appium-gestures" / "target" / "screenshots" / "w3c",
    ]


def verify_pair(before: Path, after: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "pinch_changed_preview": None,
            "still_on_detail_screen": None,
            "summary": "OPENROUTER_API_KEY not set — skip AI verify",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Image A (before pinch on photo detail):"},
                _encode(before),
                {"type": "text", "text": "Image B (after pinch on photo detail):"},
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
            "pinch_changed_preview": None,
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
            "pinch_changed_preview": False,
            "still_on_detail_screen": False,
            "summary": raw[:500],
            "skipped": False,
            "before": str(before),
            "after": str(after),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, help="Before pinch screenshot")
    parser.add_argument("--after", type=Path, help="After pinch screenshot")
    args = parser.parse_args()

    roots = default_search_roots()
    w3c = _REPO / "automation" / "appium-gestures" / "target" / "screenshots" / "w3c"
    before = args.before or _find_screenshot("ED_03_detail_before_pinch", roots)
    if before is None:
        before = _find_screenshot("before_pinch", [w3c])
    after = args.after or _find_screenshot("ED_03_detail_after_pinch", roots)
    if after is None:
        after = _find_screenshot("after_pinch", [w3c])

    missing = [
        name
        for name, path in [("before", before), ("after", after)]
        if path is None or not path.is_file()
    ]
    if missing:
        print(f"ERROR: missing screenshots: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = verify_pair(before, after)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("pinch_changed_preview") and result.get("still_on_detail_screen"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
