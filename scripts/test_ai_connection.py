#!/usr/bin/env python3
"""
Pre-flight: verify OpenRouter API with a tiny prompt. Writes build-summary/ai_status.txt
Does not use invalid models; does not block pipeline if it fails.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "build-summary" / "ai_status.txt"
MODEL = "openrouter/free"
PROMPT = "Reply with OK only."


def _write(msg: str, ok: str, err: str = "") -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"AI_STATUS={msg}"]
    if err:
        lines.append(f"ERROR={err}")
    if ok and msg == "AVAILABLE":
        lines.append("MODEL=" + MODEL)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    key = (
        os.environ.get("OpenRouterAPI", "").strip()
        or os.environ.get("OPENROUTER_API_KEY", "").strip()
        or os.environ.get("OPENROUTER_KEY", "").strip()
    )
    if not key:
        _write("UNAVAILABLE", "0", "No API key in env (OpenRouterAPI or OPENROUTER_API_KEY)")
        return 0

    url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.0,
        "max_tokens": 16,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    ref = os.environ.get("OPENROUTER_HTTP_REFERER", "")
    if ref:
        headers["HTTP-Referer"] = ref
    headers["X-Title"] = "Kodak AI health check"
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        ch = (data.get("choices") or [{}])[0]
        content = ((ch.get("message") or {}).get("content") or "").strip()
        if "ok" in content.lower():
            _write("AVAILABLE", "1", "")
            return 0
        _write("UNAVAILABLE", "0", f"Unexpected reply: {content!r}")
        return 0
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            err_body = str(e)
        _write("UNAVAILABLE", "0", f"HTTP {e.code}: {err_body}")
        return 0
    except Exception as e:
        _write("UNAVAILABLE", "0", str(e))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
