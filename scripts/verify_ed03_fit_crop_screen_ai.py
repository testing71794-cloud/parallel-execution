#!/usr/bin/env python3
"""Optional AI verification for ED_03 screenshots (OpenRouter vision). Run after Maestro test."""
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

_PROMPT = """You are validating a Kodak Step Prints Android app screenshot taken AFTER fit/crop pinch on the photo DETAIL preview (MicrosoftTeams-video 29).

The expected screen is the single-photo detail view: large photo preview in a white frame, action buttons below such as Edit, Print, Pre-Cut Stickers, and Collage. NOT gallery grid, NOT Edit Photo toolbar with filter carousel.

Reply with ONLY valid JSON (no markdown), exactly:
{"screen_correct": true, "crop_applied": true, "summary": "one short sentence"}

Rules:
- screen_correct=true if this looks like the photo detail/preview screen after pinch (Edit + Print + Collage visible).
- crop_applied=true if the preview photo framing changed or pinch visibly affected the image inside the white frame.
- Use false only when the screen is clearly wrong (error, blank, gallery grid, or Edit Photo edit canvas)."""


def _parse_json_response(raw: str) -> dict:
    text = (raw or "").strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            chunk = part.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                text = chunk
                break
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _find_screenshot(name: str, search_roots: list[Path]) -> Path | None:
    for root in search_roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(f"*{name}*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                return p
    return None


def verify_image(path: Path) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "screen_correct": None,
            "crop_applied": None,
            "summary": "OPENROUTER_API_KEY not set — skip AI verify",
            "skipped": True,
        }
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    messages = [
        {"role": "system", "content": _PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Verify this post fit/crop photo detail screenshot."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
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
            "screen_correct": None,
            "crop_applied": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
        }
    try:
        result = _parse_json_response(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
        return result
    except json.JSONDecodeError:
        return {
            "screen_correct": False,
            "crop_applied": False,
            "summary": raw[:500],
            "model_used": model_used,
            "skipped": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, help="Path to PNG/JPG screenshot")
    parser.add_argument(
        "--search",
        type=Path,
        action="append",
        default=[],
        help="Directory to search for ED_03_post_fit_crop_verify screenshot",
    )
    args = parser.parse_args()
    path = args.screenshot
    if path is None:
        roots = args.search or [
            _REPO,
            Path.home() / ".maestro" / "tests",
            Path.home() / ".maestro" / "screenshots",
            _REPO / "reports" / "editing",
        ]
        path = _find_screenshot("ED_03_post_fit_crop_verify", roots)
    if path is None or not path.is_file():
        print("ERROR: screenshot not found", file=sys.stderr)
        return 2
    result = verify_image(path)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("screen_correct") and result.get("crop_applied"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
