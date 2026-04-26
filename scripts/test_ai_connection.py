#!/usr/bin/env python3
"""
Pre-flight: verify OpenRouter API with a tiny prompt. Writes build-summary/ai_status.txt
Does not block the pipeline on failure. Never prints the API key.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "build-summary" / "ai_status.txt"
USER_PROMPT = "Reply with OK only."
# Must be >10: some free models use budget fast and return empty + finish_reason=length at low caps.
PREFLIGHT_MAX_TOKENS = int(
    (os.environ.get("OPENROUTER_TEST_MAX_TOKENS", "") or "128").strip() or 128
)
PREFLIGHT_429_RETRIES = max(
    0, min(5, int((os.environ.get("OPENROUTER_TEST_429_RETRIES", "") or "3").strip() or 3))
)
PREFLIGHT_429_BACKOFF_SEC = max(
    1.0,
    float((os.environ.get("OPENROUTER_TEST_429_BACKOFF_SEC", "") or "5").strip() or 5.0),
)
DEFAULT_BASE = "https://openrouter.ai/api/v1"


def _debug(msg: str) -> None:
    if os.environ.get("OPENROUTER_TEST_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        print(f"[openrouter-test] {msg}", flush=True)


def _redact(s: str) -> str:
    t = s or ""
    t = re.sub(r"sk-or-v1-[A-Za-z0-9\-_]{8,}", "sk-or-v1-***", t)
    t = re.sub(r"sk-[A-Za-z0-9_\-]{16,}", "sk-***", t)
    return t


def _safe_snippet(raw: str, max_len: int = 480) -> str:
    u = (raw or "").replace("\n", " ").replace("\r", " ").strip()
    u = _redact(u)
    if len(u) > max_len:
        return u[:max_len] + "…"
    return u


def _load_key_and_source() -> tuple[str, str]:
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
        v = (os.environ.get("OPENROUTER_MODEL_PRIMARY", "") or "openrouter/free").strip()
        return v or "openrouter/free"


def _fallback_model() -> str:
    try:
        from intelligent_platform import config

        return config.openrouter_model_fallback_1()
    except Exception:
        return (os.environ.get("OPENROUTER_MODEL_FALLBACK_1", "") or "").strip() or (
            "meta-llama/llama-3.3-70b-instruct:free"
        )


def _fallback2_model() -> str:
    """Optional third model when config fallback_2 is 'rules' (not an API id)."""
    try:
        from intelligent_platform import config

        s = (config.openrouter_model_fallback_2() or "").strip()
        if s and s.lower() != "rules":
            return s
    except Exception:
        pass
    s = (os.environ.get("OPENROUTER_MODEL_FALLBACK_2", "") or "").strip()
    if s and s.lower() != "rules":
        return s
    return (os.environ.get("OPENROUTER_TEST_MODEL_3", "") or "").strip() or (
        "qwen/qwen-2.5-7b-instruct:free"
    )


def _message_text(choice: dict) -> str:
    msg = (choice or {}).get("message") or {}
    c = msg.get("content")
    if c is None:
        return ""
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, list):
        parts: list[str] = []
        for p in c:
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
                parts.append(str(p.get("text", "")))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(parts).strip()
    return str(c).strip()


def _format_error_obj(err: Any) -> str:
    if err is None:
        return ""
    if isinstance(err, str):
        return _safe_snippet(err, 800)
    if isinstance(err, dict):
        code = err.get("code", err.get("type", ""))
        msg = err.get("message", err.get("metadata", ""))
        if isinstance(msg, dict):
            msg = json.dumps(msg)[:300]
        parts: list[str] = []
        if code not in (None, ""):
            parts.append(f"code={code!r}")
        if msg not in (None, ""):
            parts.append(f"message={_safe_snippet(str(msg), 500)}")
        if parts:
            return " ".join(parts)
        return _safe_snippet(json.dumps(err)[:500])
    return _safe_snippet(str(err), 500)


def _is_ok_reply(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return "ok" in t


def _chat_url() -> str:
    b = (os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE) or DEFAULT_BASE).rstrip(
        "/"
    )
    return f"{b}/chat/completions"


def _http_headers(key: str) -> dict[str, str]:
    ref = (os.environ.get("OPENROUTER_HTTP_REFERER", "") or "http://localhost").strip()
    if not ref:
        ref = "http://localhost"
    title = (
        os.environ.get("OPENROUTER_APP_TITLE", "") or "Kodak Smile Automation"
    ).strip() or "Kodak Smile Automation"
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": ref,
        "X-Title": title,
    }


def _payload(model: str, *, max_tokens: int | None = None) -> dict[str, Any]:
    mt = PREFLIGHT_MAX_TOKENS if max_tokens is None else max(16, int(max_tokens))
    return {
        "model": model,
        "messages": [{"role": "user", "content": USER_PROMPT}],
        "max_tokens": mt,
        "temperature": 0,
    }


def _single_post(
    model: str, key: str, *, max_tokens: int | None = None
) -> dict[str, Any]:
    """
    One HTTP POST. Returns keys: kind, code (HTTP status or None), detail, text (if assistant).
    kind: success_ok | success_bad_reply | http_error | empty_body | bad_json
          | top_level_error | no_choices | empty_message
    """
    url = _chat_url()
    body = json.dumps(_payload(model, max_tokens=max_tokens)).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers=_http_headers(key), method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            code = resp.getcode() or 200
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        code = int(e.code)
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception as ex:
            raw = ""
            return {
                "kind": "http_error",
                "code": code,
                "detail": f"model={model} read_error={ex!s}",
                "text": "",
            }
        d_body = _format_error_from_response_body(raw, model, code)
        return {
            "kind": "http_error",
            "code": code,
            "detail": d_body,
            "text": "",
        }
    _debug(
        f"model={model} http={code} body_len={len(raw)}"
    )
    if not (raw or "").strip():
        return {
            "kind": "empty_body",
            "code": code,
            "detail": f"model={model} HTTP {code} empty response body (0 bytes)",
            "text": "",
        }
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "kind": "bad_json",
            "code": code,
            "detail": (
                f"model={model} HTTP {code} invalid JSON ({e!s}); "
                f"raw={_safe_snippet(raw)}"
            ),
            "text": "",
        }
    if isinstance(data, dict) and data.get("error") is not None:
        emsg = _format_error_obj(data.get("error"))
        if not emsg:
            emsg = _safe_snippet(raw, 500)
        return {
            "kind": "top_level_error",
            "code": code,
            "detail": f"model={model} error field: {emsg}",
            "text": "",
        }
    chs = (data or {}).get("choices") if isinstance(data, dict) else None
    if not chs:
        u = (data or {}).get("usage") if isinstance(data, dict) else {}
        return {
            "kind": "no_choices",
            "code": code,
            "detail": f"model={model} no choices in JSON (usage={u!r}); raw_head={_safe_snippet(raw)}",
            "text": "",
        }
    text = _message_text(chs[0] if chs else {})
    if not (text or "").strip():
        fr = (chs[0] or {}).get("finish_reason", "")
        return {
            "kind": "empty_message",
            "code": code,
            "detail": (
                f"model={model} choices[0].message.content empty; "
                f"finish_reason={fr!r}; usage={(data or {}).get('usage')!r}"
            ),
            "text": "",
        }
    if _is_ok_reply(text):
        return {
            "kind": "success_ok",
            "code": code,
            "detail": "",
            "text": text,
        }
    return {
        "kind": "success_bad_reply",
        "code": code,
        "detail": f"model={model} expected reply containing 'OK', got {text!r}",
        "text": text,
    }


def _format_error_from_response_body(raw: str, model: str, code: int) -> str:
    s = (raw or "").strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            o = json.loads(s)
        except json.JSONDecodeError:
            o = None
        if isinstance(o, dict) and o.get("error") is not None:
            emsg = _format_error_obj(o.get("error"))
            if emsg:
                return f"model={model} HTTP {code} {emsg}"
    return f"model={model} HTTP {code} body={_safe_snippet(s)}"


def _write(
    status: str,
    *,
    err: str = "",
    model_part: str = "",
    key_present: str = "no",
    key_source: str = "none",
    model_tried: str = "",
) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    err_line = (err or "").replace("\n", " ").replace("\r", " ").strip()
    if not err_line and status == "UNAVAILABLE":
        err_line = "OpenRouter preflight failed (no specific detail)."
    lines = [
        f"AI_STATUS={status}",
        f"KEY_PRESENT={key_present}",
        f"KEY_SOURCE={key_source}",
    ]
    if err_line and status == "UNAVAILABLE":
        lines.append(f"ERROR={err_line[:1200]}")
    if model_part and status == "AVAILABLE":
        lines.append(f"MODEL_USED={model_part}")
        lines.append(f"MODEL={model_part}")
    if model_tried and status == "UNAVAILABLE":
        lines.append(f"MODEL_TRIED={model_tried}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def _build_model_list() -> list[str]:
    m1 = (_primary_model() or "").strip()
    m2 = (_fallback_model() or "").strip()
    m3 = (_fallback2_model() or "").strip()
    out: list[str] = []
    for m in (m1, m2, m3):
        t = (m or "").strip()
        if not t or t.lower() == "rules":
            continue
        if t not in out:
            out.append(t)
    if not out:
        out = [
            "openrouter/free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-7b-instruct:free",
        ]
    return out


def _run_one_model(model: str, key: str) -> tuple[str, str]:
    """
    Returns ("ok", "") on success, ("next", err_detail) to try next model, ("auth", 401 message) to stop.
    Implements: 5xx -> retry same model once; 429 -> backoff retries; empty_message+length -> retry w/ more tokens.
    """
    last: str = ""
    rate_429: str = ""
    for attempt in range(2):
        r = _single_post(model, key)
        kind = r.get("kind")
        code = r.get("code")
        if kind == "success_ok":
            return "ok", (r.get("text") or "")
        detail = (r.get("detail") or "").strip() or f"kind={kind!r}"
        if kind == "http_error" and (code is not None):
            c = int(code)
            if c == 401:
                return (
                    "auth",
                    f"HTTP 401: invalid or revoked API key. {_safe_snippet(detail, 500)}. "
                    "Jenkins: check Secret text credential; OPENROUTER_CREDENTIALS_ID; value must be raw key.",
                )
            if c == 400:
                return (
                    "next",
                    f"HTTP 400 (invalid request/model; no retry on same): {detail}",
                )
            if c in (402, 403):
                return "next", f"HTTP {c} (account/provider/permission): {detail}"
            if c == 429:
                # Same model, exponential-ish backoff (OpenRouter free tier often 429s).
                rate_429 = detail
                for rj in range(PREFLIGHT_429_RETRIES):
                    wait = PREFLIGHT_429_BACKOFF_SEC * (1.0 + 0.5 * rj)
                    _debug(f"429 model={model} wait={wait:.1f}s try {rj+1}/{PREFLIGHT_429_RETRIES}")
                    time.sleep(wait)
                    r2 = _single_post(model, key)
                    if r2.get("kind") == "success_ok":
                        return "ok", (r2.get("text") or "")
                    if (r2.get("code") or 0) != 429:
                        d2 = (r2.get("detail") or "").strip() or f"kind={r2.get('kind')!r}"
                        return "next", d2
                return "next", f"HTTP 429 (rate limit) after {PREFLIGHT_429_RETRIES} waits: {rate_429 or detail}"
            if 500 <= c < 600 and attempt == 0:
                _debug(f"5xx retry model={model} code={c}")
                time.sleep(1.5)
                last = detail
                continue
            if 500 <= c < 600:
                return "next", f"HTTP {c} after one retry: {last or detail}"
            return "next", detail
        if kind == "empty_message" and "finish_reason='length'" in (detail or ""):
            r3 = _single_post(model, key, max_tokens=max(256, PREFLIGHT_MAX_TOKENS * 2))
            if r3.get("kind") == "success_ok":
                return "ok", (r3.get("text") or "")
        if kind in (
            "empty_body",
            "bad_json",
            "top_level_error",
            "no_choices",
            "empty_message",
            "success_bad_reply",
        ):
            return "next", detail
        return "next", detail
    return "next", "exhausted POST attempts without success"


def main() -> int:
    key, key_src = _load_key_and_source()
    if (os.environ.get("AI_STATUS") or "").strip().lower().startswith("sk-"):
        _write(
            "UNAVAILABLE",
            err=(
                "Misconfiguration: environment variable AI_STATUS must not be set to your API key. "
                "Use OPENROUTER_API_KEY (or OpenRouterAPI) only."
            ),
            key_present="no",
            key_source=key_src,
        )
        return 0
    if not key:
        _write(
            "UNAVAILABLE",
            err=(
                "No API key in environment. Set OPENROUTER_API_KEY or "
                "Jenkins OPENROUTER_CREDENTIALS_ID to a Secret text id."
            ),
            key_present="no",
            key_source="none",
        )
        return 0
    key = key.strip().strip('"').strip("'")
    if not key:
        _write(
            "UNAVAILABLE",
            err="Key is empty after trim (check Jenkins secret for newlines).",
            key_present="no",
            key_source=key_src,
        )
        return 0
    models = _build_model_list()
    errors: list[str] = []
    tried: list[str] = []
    for m in models:
        if m in tried:
            continue
        tried.append(m)
        out, text_or_err = _run_one_model(m, key)
        if out == "ok":
            _write("AVAILABLE", model_part=m, key_present="yes", key_source=key_src)
            return 0
        if out == "auth":
            _write(
                "UNAVAILABLE",
                err=text_or_err,
                key_present="yes",
                key_source=key_src,
                model_tried=",".join(tried),
            )
            return 0
        if text_or_err:
            errors.append(text_or_err)
    merged = " | ".join(dict.fromkeys(errors)) if errors else "All model attempts failed."
    _write(
        "UNAVAILABLE",
        err=merged[:2000],
        key_present="yes",
        key_source=key_src,
        model_tried=",".join(tried),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
