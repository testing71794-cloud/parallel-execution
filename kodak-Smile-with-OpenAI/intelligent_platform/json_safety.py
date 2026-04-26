"""Parse model output into strict failure-analysis JSON with robust fallbacks."""

from __future__ import annotations

import json
import re
from typing import Any


def safe_json_parse(text: str) -> dict[str, Any]:
    """
    Best-effort JSON extraction from model output.
    On total failure, returns a stable 'unknown' shell (pipeline never breaks).
    """
    raw = (text or "").strip()
    if not raw:
        return _fallback_empty()

    # Direct parse
    try:
        return _normalize_obj(json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Fenced ```json ... ```
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I):
        block = m.group(1).strip()
        try:
            return _normalize_obj(json.loads(block))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    # First balanced {...} scan (longest candidate first)
    for candidate in _json_object_candidates(raw):
        try:
            return _normalize_obj(json.loads(candidate))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    return {
        "category": "unknown",
        "root_cause": raw[:4000],
        "suggestion": "Manual investigation required",
        "is_test_issue": False,
        "confidence": 0.0,
    }


def _fallback_empty() -> dict[str, Any]:
    return {
        "category": "unknown",
        "root_cause": "",
        "suggestion": "Manual investigation required",
        "is_test_issue": False,
        "confidence": 0.0,
    }


def _normalize_obj(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    return {
        "category": str(obj.get("category", "unknown"))[:64],
        "root_cause": str(obj.get("root_cause", ""))[:4000],
        "suggestion": str(obj.get("suggestion", ""))[:4000],
        "is_test_issue": bool(obj.get("is_test_issue", False)),
        "confidence": float(obj.get("confidence", 0.0)),
    }


def _json_object_candidates(text: str) -> list[str]:
    out: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start : i + 1].strip()
                if len(candidate) > 15:
                    out.append(candidate)
                start = -1
    out.sort(key=len, reverse=True)
    return out
