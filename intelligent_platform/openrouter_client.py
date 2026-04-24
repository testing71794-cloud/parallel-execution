"""
OpenRouter API integration — explicit model IDs, no auto-routing.
https://openrouter.ai/docs
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("intelligent_platform.openrouter")


class OpenRouterHTTPError(RuntimeError):
    """HTTP error from OpenRouter; .code is HTTP status if known."""

    def __init__(self, message: str, *, code: int | None = None, body: str = ""):
        super().__init__(message)
        self.code = code
        self.body = body

# Explicit model IDs (no provider auto-selection) — free-tier primary + reliable fallback
MODEL_PRIMARY = "openrouter/free"
MODEL_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SEC = 120

# Deterministic generation
TEMPERATURE = 0.1
MAX_TOKENS = 300


def call_openrouter(
    messages: list[dict[str, str]],
    model: str,
    *,
    api_key: str,
    base_url: str,
    http_referer: str = "",
    app_title: str = "Kodak Intelligent Platform",
) -> str:
    """
    POST /chat/completions. Returns assistant message content (string).
    Raises on HTTP error, network error, or empty content.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    if app_title:
        headers["X-Title"] = app_title

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            pass
        raise OpenRouterHTTPError(
            f"OpenRouter HTTP {e.code}: {err_body or e.reason}",
            code=e.code,
            body=err_body,
        ) from e
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise RuntimeError(f"OpenRouter network error: {e}") from e

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter: empty choices")
    content = (choices[0].get("message") or {}).get("content")
    if content is None or (isinstance(content, str) and not content.strip()):
        raise RuntimeError("OpenRouter: no message content")
    if not isinstance(content, str):
        content = str(content)
    logger.debug("OpenRouter model=%s response length=%s", model, len(content))
    return content.strip()
