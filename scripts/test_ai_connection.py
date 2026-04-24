#!/usr/bin/env python3
"""
Pre-flight: verify OpenRouter API with a tiny prompt. Writes build-summary/ai_status.txt
Does not block the pipeline on failure. Never prints the API key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "build-summary" / "ai_status.txt"
PROMPT = "Reply with OK only."


def _load_key_and_source() -> tuple[str, str]:
    """Single source of truth with intelligent_platform.config (OpenRouterAPI, OPENROUTER_API_KEY, …)."""
    try:
        from intelligent_platform import config

        return (config.openrouter_api_key() or "").strip(), (
            config.openrouter_key_env_name_used() or "none"
        )
    except Exception:
        k = (
            (os.environ.get("OpenRouterAPI", "") or "").strip()
            or (os.environ.get("OPENROUTER_API_KEY", "") or "").strip()
            or (os.environ.get("OPENROUTER_KEY", "") or "").strip()
        )
        for name in ("OpenRouterAPI", "OPENROUTER_API_KEY", "OPENROUTER_KEY"):
            if (os.environ.get(name) or "").strip():
                return k, name
        return k, "none" if not k else "unknown"


def _primary_model() -> str:
    try:
        from intelligent_platform import config

        return config.openrouter_model_primary()
    except Exception:
        return (os.environ.get("OPENROUTER_MODEL_PRIMARY", "") or "openrouter/free").strip() or "openrouter/free"


def _write(
    status: str,
    *,
    err: str = "",
    model_part: str = "",
    key_present: str = "no",
    key_source: str = "none",
) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"AI_STATUS={status}",
        f"KEY_PRESENT={key_present}",
        f"KEY_SOURCE={key_source}",
    ]
    if err:
        lines.append(f"ERROR={err}")
    if model_part and status == "AVAILABLE":
        lines.append(f"MODEL_USED={model_part}")
    # Back-compat for older consumers
    if model_part and status == "AVAILABLE":
        lines.append(f"MODEL={model_part}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    key, key_src = _load_key_and_source()
    if not key:
        _write(
            "UNAVAILABLE",
            err=(
                "No API key in environment. "
                "Jenkins: bind the credential to OPENROUTER_API_KEY, OpenRouterAPI, or OPENROUTER_KEY."
            ),
            key_present="no",
            key_source="none",
        )
        return 0
    m = _primary_model()
    url = (
        os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        + "/chat/completions"
    )
    payload = {
        "model": m,
        "messages": [
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.0,
        "max_tokens": 16,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
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
            _write("AVAILABLE", err="", model_part=m, key_present="yes", key_source=key_src)
            return 0
        _write(
            "UNAVAILABLE",
            err=f"Unexpected reply: {content!r}",
            key_present="yes",
            key_source=key_src,
        )
        return 0
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            err_body = str(e)
        _write(
            "UNAVAILABLE",
            err=f"HTTP {e.code}: {err_body}",
            key_present="yes",
            key_source=key_src,
        )
        return 0
    except Exception as e:
        _write(
            "UNAVAILABLE",
            err=str(e),
            key_present="yes" if key else "no",
            key_source=key_src,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
