"""
Post-flow AI analysis using OpenRouter (JUnit + log context).
HTTP 429: retry after 5s, max 3 attempts total.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger("orch.ai")

# Reuse project config / client where possible
try:
    from intelligent_platform import config as _cfg
    from intelligent_platform.json_safety import safe_json_parse
    from intelligent_platform.openrouter_client import (
        OpenRouterHTTPError,
        call_openrouter,
    )
except Exception:  # pragma: no cover - allow minimal import in isolation
    _cfg = None  # type: ignore
    safe_json_parse = None  # type: ignore
    call_openrouter = None  # type: ignore
    OpenRouterHTTPError = Exception  # type: ignore


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[-1]
    return tag


def extract_junit_summary(junit_path: Path, flow_display: str) -> tuple[str, str, str]:
    """
    Returns (overall_status, test_name, failure_message).
    overall_status: PASS | FAIL | ERROR | UNKNOWN
    """
    if not junit_path.is_file():
        return "UNKNOWN", flow_display, "JUnit file not produced"

    try:
        root = ET.parse(junit_path).getroot()
    except (ET.ParseError, OSError) as e:
        return "UNKNOWN", flow_display, f"JUnit parse error: {e}"

    cases = list(root.iter("testcase"))
    failed_parts: list[str] = []
    names: list[str] = []

    for case in cases:
        name = case.get("name") or "unknown"
        classname = case.get("classname") or ""
        label = f"{classname} :: {name}".strip(" :") or name
        names.append(label)
        fail = case.find("failure")
        err_el = case.find("error")
        if fail is None:
            for el in case:
                if _local(el.tag) == "failure":
                    fail = el
                    break
        if err_el is None:
            for el in case:
                if _local(el.tag) == "error":
                    err_el = el
                    break
        node = fail if fail is not None else err_el
        if node is None:
            continue
        msg = node.get("message") or ""
        body = (node.text or "").strip()
        failed_parts.append(f"{label}: {msg}\n{body}".strip())

    if failed_parts:
        return "FAIL", names[0] if names else flow_display, "\n---\n".join(failed_parts)[:8000]

    if not cases:
        # Some exports only have testsuite-level metadata
        suite_msgs: list[str] = []
        for el in root.iter():
            if _local(el.tag) in ("failure", "error"):
                msg = el.get("message") or ""
                body = (el.text or "").strip()
                suite_msgs.append(f"{msg}\n{body}".strip())
        for suite in root.iter():
            if _local(suite.tag) != "testsuite":
                continue
            fails = int(suite.get("failures") or 0)
            errs = int(suite.get("errors") or 0)
            if fails + errs > 0:
                hint = " ".join(suite_msgs) or f"testsuite reports failures={fails} errors={errs}"
                return "FAIL", flow_display, hint[:8000]
        return "UNKNOWN", flow_display, "No testcase elements in JUnit"

    skipped = [c for c in cases if c.find("skipped") is not None or any(_local(x.tag) == "skipped" for x in c)]
    if skipped and len(skipped) == len(cases):
        return "ERROR", names[0] if names else flow_display, "All tests skipped"

    return "PASS", names[0] if names else flow_display, ""


def _system_prompt() -> str:
    return (
        "You are a senior mobile QA automation engineer. "
        "Respond ONLY with compact JSON: "
        '{"root_cause":"...","suggested_fix":"..."} '
        "No markdown, no extra keys."
    )


def _user_prompt(test_name: str, status: str, failure_message: str, log_excerpt: str) -> str:
    return (
        f"Test name: {test_name}\n"
        f"Status: {status}\n"
        f"Failure message (from JUnit):\n{failure_message or '(none)'}\n\n"
        f"Log excerpt:\n{(log_excerpt or '')[:12000]}\n"
    )


def _format_ai_line(parsed: dict[str, Any]) -> str:
    rc = str(parsed.get("root_cause", "")).strip()
    sf = str(parsed.get("suggested_fix", "")).strip()
    if rc and sf:
        return f"{rc} Suggested fix: {sf}"
    return rc or sf or "AI returned empty fields."


def analyze_flow_failure(
    *,
    test_name: str,
    status: str,
    failure_message: str,
    log_excerpt: str,
    model: str | None = None,
) -> str:
    """
    Call OpenRouter for root cause + fix. On failure returns a clear error string
    (never raises to the orchestrator).
    """
    if status.upper() in ("PASS", ""):
        return ""

    if not _cfg or not call_openrouter or not safe_json_parse:
        return "AI Analysis Failed (intelligent_platform not available)"

    api_key = _cfg.openrouter_api_key()
    if not api_key:
        logger.info("No OpenRouter API key; skipping AI")
        return "AI Analysis Failed (no API key)"

    m = (model or _cfg.openrouter_model_primary() or "openrouter/free").strip()
    messages = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _user_prompt(test_name, status, failure_message, log_excerpt),
        },
    ]

    # HTTP 429: up to 3 attempts total, 5s backoff between retries (enterprise rate limits).
    last_err = ""
    for attempt in range(3):
        try:
            raw = call_openrouter(
                messages,
                m,
                api_key=api_key,
                base_url=_cfg.OPENROUTER_BASE_URL,
                http_referer=_cfg.OPENROUTER_HTTP_REFERER,
                app_title=_cfg.OPENROUTER_APP_TITLE,
            )
            parsed = safe_json_parse(raw)
            line = _format_ai_line(parsed)
            logger.info("AI analysis ok (attempt %s)", attempt + 1)
            return line[:4000]
        except OpenRouterHTTPError as e:  # type: ignore[misc]
            code = getattr(e, "code", None) or 0
            last_err = str(e)
            logger.warning("OpenRouter error attempt %s: %s", attempt + 1, e)
            if code == 429 and attempt < 2:
                logger.warning("HTTP 429 from OpenRouter; retry %s/3 after 5s", attempt + 1)
                time.sleep(5)
                continue
            break
        except urllib.error.HTTPError as e:
            last_err = str(e)
            if e.code == 429 and attempt < 2:
                logger.warning("HTTP 429; retry %s/3 after 5s", attempt + 1)
                time.sleep(5)
                continue
            break
        except Exception as e:
            last_err = str(e)
            logger.exception("AI call failed")
            break

    return f"AI Analysis Failed ({last_err[:500]})"


def read_log_tail(path: Path, max_bytes: int = 24_000) -> str:
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""
