"""
AI failure analysis — OpenRouter (DeepSeek V3.2 primary, Llama 3.3 70B fallback), strict JSON, rule fallback.
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
    call_openrouter,
)

logger = logging.getLogger("intelligent_platform.ai")

_SYSTEM_STRICT_JSON = "You are a precise and strict JSON generator."

# Full prompt (failure payload injected as JSON; example uses escaped braces in .format)
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
    """True if model output is a real classification (not total parse fallback)."""
    if str(d.get("category", "")).lower() == "unknown":
        return False
    if not str(d.get("root_cause", "")).strip():
        return False
    sug = str(d.get("suggestion", ""))
    if sug == "Manual investigation required" and float(d.get("confidence", 0)) == 0.0:
        return False
    return True


def _try_openrouter_model(
    failure: dict[str, Any], model: str, api_key: str
) -> dict[str, Any] | None:
    user_prompt = _build_user_prompt(failure)
    messages = [
        {"role": "system", "content": _SYSTEM_STRICT_JSON},
        {"role": "user", "content": user_prompt},
    ]
    attempts = 1 + max(0, min(2, config.AI_MAX_RETRIES))
    last: Exception | None = None
    for attempt in range(attempts):
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
            return _coerce_result(parsed)
        except Exception as e:
            last = e
            logger.warning(
                "OpenRouter model=%s attempt %s failed: %s", model, attempt + 1, e
            )
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    if last:
        logger.error("Model %s exhausted: %s", model, last)
    return None


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
    OpenRouter → primary (DeepSeek) → explicit fallback (Llama) → ATP rules.
    """
    if not config.openrouter_configured():
        logger.info("OPENROUTER_API_KEY not set — rule-based analyzer")
        return _rule_analyze(failure)

    key = config.OPENROUTER_API_KEY
    r1 = _try_openrouter_model(failure, MODEL_PRIMARY, key)
    if r1 and _analysis_usable(r1):
        logger.info(
            "AI analysis result (primary %s): category=%s conf=%.2f",
            MODEL_PRIMARY,
            r1["category"],
            r1["confidence"],
        )
        return r1

    logger.warning("Primary model unusable or failed — trying explicit fallback: %s", MODEL_FALLBACK)
    r2 = _try_openrouter_model(failure, MODEL_FALLBACK, key)
    if r2 and _analysis_usable(r2):
        logger.info(
            "AI analysis result (fallback %s): category=%s conf=%.2f",
            MODEL_FALLBACK,
            r2["category"],
            r2["confidence"],
        )
        return r2

    note = f"OpenRouter: primary={MODEL_PRIMARY} fallback={MODEL_FALLBACK} unavailable or unusable"
    logger.error("%s — using rules", note)
    return _rule_analyze(failure, note=note)
