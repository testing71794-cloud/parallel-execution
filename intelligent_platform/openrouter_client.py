"""
OpenRouter API integration — explicit model IDs, no auto-routing.
https://openrouter.ai/docs
"""

from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import time
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

# Default model IDs (env overrides: intelligent_platform.config.openrouter_model_*)
MODEL_PRIMARY = "openrouter/free"
MODEL_FALLBACK = "meta-llama/llama-3.3-70b-instruct:free"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SEC = 120
VISION_TIMEOUT_SEC = max(15, int(os.environ.get("OPENROUTER_VISION_TIMEOUT_SEC", "45")))

# Deterministic generation
TEMPERATURE = 0.1
MAX_TOKENS = 300


def _ssl_context() -> ssl.SSLContext:
    try:
        from intelligent_platform import config

        verify = config.openrouter_ssl_verify()
    except Exception:
        verify = True
    if verify:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def call_openrouter(
    messages: list[dict[str, Any]],
    model: str,
    *,
    api_key: str,
    base_url: str,
    http_referer: str = "",
    app_title: str = "Kodak Intelligent Platform",
    max_tokens: int | None = None,
    timeout_sec: int | None = None,
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
        "max_tokens": max_tokens if max_tokens is not None else MAX_TOKENS,
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
        with urllib.request.urlopen(
            req,
            timeout=timeout_sec if timeout_sec is not None else DEFAULT_TIMEOUT_SEC,
            context=_ssl_context(),
        ) as resp:
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


def call_openrouter_vision(
    messages: list[dict[str, Any]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    http_referer: str = "",
    app_title: str = "Kodak Intelligent Platform",
    max_tokens: int = 400,
) -> tuple[str, str]:
    """Try primary vision model then fallbacks. Returns (content, model_used)."""
    try:
        from intelligent_platform.config import openrouter_vision_model_chain

        candidates = list(openrouter_vision_model_chain())
    except Exception:
        candidates = [model] if model else []
    if model and model not in candidates:
        candidates.insert(0, model)
    max_rounds = max(1, int(os.environ.get("OPENROUTER_VISION_MAX_ROUNDS", "2")))
    backoff_sec = 2.0
    vision_timeout = VISION_TIMEOUT_SEC
    last_error: Exception | None = None
    for round_idx in range(max_rounds):
        rate_limited_or_empty = False
        for idx, candidate in enumerate(candidates):
            if idx > 0:
                logger.info("OpenRouter vision fallback: trying model=%s", candidate)
            try:
                content = call_openrouter(
                    messages,
                    candidate,
                    api_key=api_key,
                    base_url=base_url,
                    http_referer=http_referer,
                    app_title=app_title,
                    max_tokens=max_tokens,
                    timeout_sec=vision_timeout,
                )
                return content, candidate
            except OpenRouterHTTPError as e:
                last_error = e
                if e.code == 429 or (e.code is not None and 500 <= e.code < 600):
                    rate_limited_or_empty = True
                    logger.warning("OpenRouter vision model=%s transient error: %s", candidate, e)
                    continue
                if e.code in {400, 402, 404}:
                    logger.warning("OpenRouter vision model=%s unavailable: %s", candidate, e)
                    continue
                raise
            except RuntimeError as e:
                last_error = e
                rate_limited_or_empty = True
                logger.warning("OpenRouter vision model=%s returned no usable content: %s", candidate, e)
                continue
        if not rate_limited_or_empty or round_idx == max_rounds - 1:
            break
        logger.warning(
            "OpenRouter vision: all candidates rate-limited on round %s; retrying in %ss",
            round_idx + 1,
            backoff_sec,
        )
        time.sleep(backoff_sec)
    if last_error:
        raise last_error
    raise RuntimeError("OpenRouter vision: no models available")
