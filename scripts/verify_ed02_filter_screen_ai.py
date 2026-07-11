#!/usr/bin/env python3
"""Optional AI verification for ED_02 screenshots (OpenRouter vision). Run after Maestro test."""
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

_PROMPT = """You are validating a Kodak Step Prints mobile app screenshot after applying a photo filter.

Answer ONLY with JSON: {"screen_correct": true/false, "filter_applied": true/false, "summary": "one sentence"}

screen_correct: edit photo screen visible with editing toolbar (Filter, Frames, Stickers, etc.)
filter_applied: photo preview shows an obvious filter effect (vintage/sepia/warm grade), not unfiltered original"""


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
            "filter_applied": None,
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
                {"type": "text", "text": "Verify this post-filter edit screen screenshot."},
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
            "filter_applied": None,
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
        }
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
        return result
    except json.JSONDecodeError:
        return {"screen_correct": False, "filter_applied": False, "summary": raw[:500], "skipped": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, help="Path to PNG/JPG screenshot")
    parser.add_argument(
        "--search",
        type=Path,
        action="append",
        default=[],
        help="Directory to search for ED_02_post_filter_verify screenshot",
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
        path = _find_screenshot("ED_02_post_filter_verify", roots)
    if path is None or not path.is_file():
        print("ERROR: screenshot not found", file=sys.stderr)
        return 2
    result = verify_image(path)
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return 0
    if result.get("screen_correct") and result.get("filter_applied"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
