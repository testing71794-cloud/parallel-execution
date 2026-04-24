"""
AI failure analysis — OpenRouter (configurable primary + fallbacks), strict JSON, rule fallback.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from . import config
from .json_safety import safe_json_parse
from .openrouter_client import (
    MODEL_FALLBACK,
    MODEL_PRIMARY,
    OpenRouterHTTPError,
    call_openrouter,
)

logger = logging.getLogger("intelligent_platform.ai")

_SYSTEM_STRICT_JSON = "You are a precise and strict JSON generator."

_ANALYSIS_USER_PROMPT = """You are an expert mobile QA automation debugger.

Your job is to analyze a FAILED test case and determine the REAL root cause.

Think step-by-step internally but DO NOT output your reasoning.

---

## Instructions:

1. Understand the failure carefully
2. Identify the MOST LIKELY root cause (not generic)
3. Classify failure into ONE category:
   - locator → element not found, wrong selector
   - timing → wait/sync issues, timeout
   - api → backend/API failure, bad response
   - crash → app crash or exception
   - assertion → validation mismatch

4. Decide:
   - Is this a TEST issue or APP issue?

---

## Output Rules (STRICT):

- Output ONLY valid JSON
- NO explanation
- NO extra text
- NO markdown
- NO comments

---

## JSON Format:

{{
  "category": "locator | timing | api | crash | assertion",
  "root_cause": "clear and specific explanation",
  "suggestion": "actionable fix (what exactly to do)",
  "is_test_issue": true/false,
  "confidence": 0.0
}}

---

## Failure Data:

{failure_data}"""


def _build_user_prompt(failure: dict[str, Any]) -> str:
    block = json.dumps(failure, ensure_ascii=False, indent=2)[:15000]
    return _ANALYSIS_USER_PROMPT.format(failure_data=block)


def _coerce_result(parsed: dict[str, Any]) -> dict[str, Any]:
    c = str(parsed.get("category", "assertion")).lower()
    for sep in ("|", ","):
        if sep in c:
            c = c.split(sep)[0].strip()
    allowed = ("locator", "timing", "api", "crash", "assertion", "unknown")
    if c not in allowed:
        c = "assertion"
    conf = float(parsed.get("confidence", 0.0))
    if conf > 1.0:
        conf = min(1.0, conf / 100.0)
    conf = max(0.0, min(1.0, conf))
    return {
        "category": c,
        "root_cause": str(parsed.get("root_cause", ""))[:2000],
        "confidence": conf,
        "suggestion": str(parsed.get("suggestion", ""))[:4000],
        "is_test_issue": bool(parsed.get("is_test_issue", True)),
    }


def _analysis_usable(d: dict[str, Any]) -> bool:
    if str(d.get("category", "")).lower() == "unknown":
        return False
    if not str(d.get("root_cause", "")).strip():
        return False
    sug = str(d.get("suggestion", ""))
    if sug == "Manual investigation required" and float(d.get("confidence", 0)) == 0.0:
        return False
    return True


def _is_api_model_id(s: str) -> bool:
    t = (s or "").strip()
    if not t or t.lower() == "rules":
        return False
    return "/" in t


def _iter_api_models() -> list[str]:
    out: list[str] = []
    for m in (
        config.openrouter_model_primary(),
        config.openrouter_model_fallback_1(),
        config.openrouter_model_fallback_2(),
    ):
        if _is_api_model_id(m) and m not in out:
            out.append(m)
    return out


def _call_model_with_policy(
    failure: dict[str, Any], model: str, api_key: str
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns (coerced_result, signal). signal: None = success, '401' = stop all OpenRouter,
    '400' = bad request / invalid model (try next), 'exhausted' = try next after retries.
    """
    user_prompt = _build_user_prompt(failure)
    messages = [
        {"role": "system", "content": _SYSTEM_STRICT_JSON},
        {"role": "user", "content": user_prompt},
    ]
    for attempt in range(2):
        try:
            text = call_openrouter(
                messages,
                model,
                api_key=api_key,
                base_url=config.OPENROUTER_BASE_URL,
                http_referer=config.OPENROUTER_HTTP_REFERER,
                app_title=config.OPENROUTER_APP_TITLE,
            )
            logger.info(
                "OpenRouter success model=%s (truncated): %s", model, text[:600]
            )
            parsed = safe_json_parse(text)
            return _coerce_result(parsed), None
        except OpenRouterHTTPError as e:
            code = e.code or 0
            logger.warning("OpenRouter model=%s HTTP %s: %s", model, code, e)
            if code == 401:
                logger.error(
                    "OpenRouter API key is invalid or missing (HTTP 401) — use rule-based fallback"
                )
                return None, "401"
            if code == 400:
                # Invalid model / bad request — do not retry the same model
                return None, "400"
            if code == 429 and attempt == 0:
                time.sleep(2.0)
                continue
            if code == 429:
                return None, "exhausted"
            if 500 <= code < 600 and attempt == 0:
                time.sleep(1.5)
                continue
            if 500 <= code < 600:
                return None, "exhausted"
            if attempt == 0:
                time.sleep(1.0)
                continue
            return None, "exhausted"
        except Exception as e:
            logger.warning("OpenRouter model=%s attempt %s failed: %s", model, attempt + 1, e)
            if attempt == 0:
                time.sleep(1.2)
                continue
            return None, "exhausted"
    return None, "exhausted"


def _read_global_ai_status() -> str:
    p = config.workspace_root() / "build-summary" / "ai_status.txt"
    if not p.is_file():
        return "NOT_CHECKED"
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().upper().startswith("AI_STATUS="):
                return line.split("=", 1)[1].strip() or "UNKNOWN"
    except OSError:
        pass
    return "UNKNOWN"


def _mark_openrouter(
    d: dict[str, Any], *, model_used: str, global_status: str
) -> dict[str, Any]:
    o = {**d}
    o["source_label"] = "OpenRouter"
    o["model_used"] = model_used
    o["analysis_source"] = "OpenRouter"
    o["ai_status"] = global_status
    return o


def _mark_rules(d: dict[str, Any], *, global_status: str) -> dict[str, Any]:
    o = {**d}
    o["source_label"] = "Rule-based fallback"
    o["model_used"] = "rules"
    o["analysis_source"] = "Rule-based fallback"
    o["ai_status"] = global_status
    return o


# Rule-based patterns (final fallback; aligned with prior ATP rules)
_FIX_PATTERNS: list[dict[str, Any]] = [
    {
        "match": re.compile(r"imageRelativelayout|imageRelative", re.I),
        "category": "locator",
        "root_cause": "Element id not found (layout id drift or removed).",
        "suggestion": "Replace with coordinate tap or updated id from hierarchy dump.",
        "is_test_issue": True,
        "confidence": 0.9,
    },
    {
        "match": re.compile(
            r"assertion is false.*visible|KODAK SMILE.*visible", re.I | re.S
        ),
        "category": "timing",
        "root_cause": "Flaky or state-dependent visibility before home/assert.",
        "suggestion": "Add waitForAnimationToEnd, wait, and conditional popups before assertVisible.",
        "is_test_issue": True,
        "confidence": 0.85,
    },
    {
        "match": re.compile(r"element not found|id matching regex", re.I),
        "category": "locator",
        "root_cause": "Selector did not match any element in hierarchy.",
        "suggestion": "assertVisible for screen first; use stable id; scrollUntilVisible if list.",
        "is_test_issue": True,
        "confidence": 0.8,
    },
    {
        "match": re.compile(
            r"\b(printing|printer|print job|out of paper|cool ?down)\b", re.I
        ),
        "category": "api",
        "root_cause": "Print pipeline or printer hardware state issue.",
        "suggestion": "Verify printer connection, paper, and waitForPrinting / pairing flows.",
        "is_test_issue": False,
        "confidence": 0.7,
    },
    {
        "match": re.compile(r"bluetooth|pairing|connect", re.I),
        "category": "api",
        "root_cause": "Bluetooth / pairing flow or OS dialog interference.",
        "suggestion": "Retry search; handle Allow/Pair dialogs; increase waits.",
        "is_test_issue": False,
        "confidence": 0.75,
    },
    {
        "match": re.compile(r"permission|allow|denied", re.I),
        "category": "assertion",
        "root_cause": "Permission dialog not handled or timing.",
        "suggestion": "runFlow when visible for Allow / While using the app.",
        "is_test_issue": True,
        "confidence": 0.85,
    },
    {
        "match": re.compile(r"java\.lang|FATAL EXCEPTION|AndroidRuntime", re.I),
        "category": "crash",
        "root_cause": "Application or framework crash during step.",
        "suggestion": "Capture logcat; check regression in app build; narrow repro steps.",
        "is_test_issue": False,
        "confidence": 0.65,
    },
]


def _rule_analyze(failure: dict[str, Any], note: str | None = None) -> dict[str, Any]:
    msg = f"{failure.get('error_message','')} {failure.get('step_failed','')}".strip()
    for p in _FIX_PATTERNS:
        if p["match"].search(msg):
            out = {
                "category": p["category"],
                "root_cause": p["root_cause"],
                "confidence": float(p["confidence"]),
                "suggestion": p["suggestion"],
                "is_test_issue": bool(p["is_test_issue"]),
            }
            if note:
                out["root_cause"] = f"{out['root_cause']} [{note}]"
            return out
    out = {
        "category": "assertion",
        "root_cause": "Unclassified failure — inspect raw log and screen state.",
        "confidence": 0.45,
        "suggestion": (
            "Add waits and popup handling; verify selectors against live hierarchy; "
            "see Maestro docs for stable patterns."
        ),
        "is_test_issue": True,
    }
    if note:
        out["root_cause"] = f"{out['root_cause']} [{note}]"
    return out


def analyze_failure(failure: dict[str, Any]) -> dict[str, Any]:
    """
    OpenRouter → each configured API model in order (primary, fallback, …) → rules.
    """
    global_s = _read_global_ai_status()
    logger.info(
        "OpenRouter key present: %s | build AI_STATUS file: %s | models to try: %s",
        "yes" if config.openrouter_key_present() else "no",
        global_s,
        _iter_api_models(),
    )

    if config.ai_health_marks_unavailable():
        logger.info("AI health check: UNAVAILABLE — rule-based analyzer")
        d = _rule_analyze(failure, note="ai_status.txt: UNAVAILABLE")
        return _mark_rules(d, global_status=global_s)

    if not config.openrouter_configured():
        logger.info("OpenRouter API key not set (use OpenRouterAPI) — rule-based analyzer")
        d = _rule_analyze(failure, note="no API key in env (OpenRouterAPI / OPENROUTER_API_KEY)")
        return _mark_rules(d, global_status=global_s)

    key = config.openrouter_api_key()
    for model in _iter_api_models():
        logger.info("OpenRouter: trying model=%s", model)
        r, sig = _call_model_with_policy(failure, model, key)
        if sig == "401":
            d = _rule_analyze(
                failure, note="OpenRouter HTTP 401 — key invalid or missing; rule-based"
            )
            return _mark_rules(d, global_status=global_s)
        if r and _analysis_usable(r):
            logger.info(
                "AI analysis (OpenRouter) model=%s: category=%s conf=%.2f",
                model,
                r["category"],
                r["confidence"],
            )
            return _mark_openrouter(r, model_used=model, global_status=global_s)
        logger.warning("Model %s not usable (sig=%s) — next fallback or rules", model, sig)

    note = (
        f"OpenRouter: all models { _iter_api_models() } failed or returned unusable output"
    )
    logger.error("%s — using rules", note)
    d = _rule_analyze(failure, note=note)
    return _mark_rules(d, global_status=global_s)
