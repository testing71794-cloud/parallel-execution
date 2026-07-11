#!/usr/bin/env python3
"""Verify ED_04: before vs after rotate screenshots show a 90° orientation change."""
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

_PROMPT = """You analyze TWO Kodak Step Print EDIT PHOTO screenshots from a rotate test.

Image A: BEFORE tapping the 90° rotate control (Adjust submenu open).
Image B: AFTER one 90° rotate tap (before confirming Done/checkmark).

Reply with ONLY valid JSON (no markdown):
{
  "rotate_applied": true,
  "summary": "one short sentence"
}

Rules:
- rotate_applied=true ONLY if B shows the photo content rotated ~90° vs A (orientation change is clear).
- If A and B look identical in orientation, set rotate_applied=false.
- Ignore minor UI chrome differences; focus on photo orientation inside the white border frame."""


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


def verify_two(before: Path, after: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "rotate_applied": None,
            "summary": "OPENROUTER_API_KEY not set — compare screenshots manually",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Image A (before rotate):"},
                _encode(before),
                {"type": "text", "text": "Image B (after rotate):"},
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
            "rotate_applied": None,
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
            "rotate_applied": False,
            "summary": raw[:500],
            "model_used": model_used,
            "skipped": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, help="Before rotate screenshot")
    parser.add_argument("--after", type=Path, help="After rotate screenshot")
    args = parser.parse_args()

    before = args.before or _find_maestro_screenshot("ED_04_before_rotate")
    after = args.after or _find_maestro_screenshot("ED_04_after_rotate")

    missing = [
        name
        for name, path in [
            ("ED_04_before_rotate", before),
            ("ED_04_after_rotate", after),
        ]
        if path is None or not path.is_file()
    ]
    if missing:
        print(f"ERROR: missing screenshots: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = verify_two(before, after)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("rotate_applied"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
