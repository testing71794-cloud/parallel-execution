"""Shared helpers for ED OpenRouter screenshot verification."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from intelligent_platform.config import (
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    openrouter_api_key,
    openrouter_model_vision,
)
from intelligent_platform.openrouter_client import call_openrouter_vision

REPO = Path(__file__).resolve().parents[1]


def parse_json_response(raw: str) -> dict:
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


def find_maestro_screenshot(name: str) -> Path | None:
    roots = [
        REPO / "reports" / "atp_editing",
        REPO / "reports" / "editing",
        REPO / "reports",
        REPO,
        Path.home() / ".maestro" / "tests",
        Path.home() / ".maestro" / "screenshots",
        REPO / "reports" / "printing",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob(f"*{name}*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.suffix.lower() == ".png":
                return p
    return None


def encode_image(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def verify_pair(
    before: Path,
    after: Path,
    *,
    prompt: str,
    before_label: str,
    after_label: str,
    pass_keys: list[str],
) -> dict:
    key = openrouter_api_key()
    if not key:
        return {
            "summary": "OPENROUTER_API_KEY not set — compare screenshots manually",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": before_label},
                encode_image(before),
                {"type": "text", "text": after_label},
                encode_image(after),
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
            "summary": f"OpenRouter unavailable: {e}",
            "skipped": True,
            "before": str(before),
            "after": str(after),
        }
    try:
        result = parse_json_response(raw)
        if isinstance(result, dict):
            result["model_used"] = model_used
            result["before"] = str(before)
            result["after"] = str(after)
            result["_pass"] = all(result.get(k) for k in pass_keys)
        return result
    except json.JSONDecodeError:
        return {
            "summary": raw[:500],
            "model_used": model_used,
            "skipped": False,
            "_pass": False,
            "before": str(before),
            "after": str(after),
        }
