"""
Excel-oriented failure analysis: OpenRouter + rule fallback; never leave failed rows blank.
Respects build-summary/ai_status.txt: AI_STATUS=UNAVAILABLE skips OpenRouter; otherwise
uses key from OpenRouterAPI (primary) when not blocked.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _read_openrouter_key() -> str:
    return (
        (os.environ.get("OpenRouterAPI", "") or "").strip()
        or (os.environ.get("OPENROUTER_API_KEY", "") or "").strip()
        or (os.environ.get("OPENROUTER_KEY", "") or "").strip()
    )


def _read_build_ai_status_block() -> dict[str, str]:
    """Values from build-summary/ai_status.txt; never includes secrets."""
    p = REPO / "build-summary" / "ai_status.txt"
    d: dict[str, str] = {
        "ai_status": "NOT_CHECKED",
        "model_used_health": "",
        "key_present": "no",
    }
    d["key_present"] = "yes" if _read_openrouter_key() else "no"
    if not p.is_file():
        return d
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s.upper().startswith("AI_STATUS="):
                d["ai_status"] = s.split("=", 1)[1].strip() or d["ai_status"]
            elif s.upper().startswith("MODEL_USED="):
                d["model_used_health"] = s.split("=", 1)[1].strip() or d["model_used_health"]
            elif s.upper().startswith("MODEL=") and not d.get("model_used_health"):
                d["model_used_health"] = s.split("=", 1)[1].strip() or d["model_used_health"]
            elif s.upper().startswith("KEY_PRESENT="):
                d["key_present"] = s.split("=", 1)[1].strip() or d["key_present"]
    except OSError:
        pass
    if _read_openrouter_key() and d.get("key_present") == "no":
        d["key_present"] = "yes"
    return d


def _read_ai_status_unavailable() -> bool:
    p = REPO / "build-summary" / "ai_status.txt"
    if not p.is_file():
        return False
    try:
        return "AI_STATUS=UNAVAILABLE" in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _read_log_tail(p: Path, max_bytes: int = 120_000) -> str:
    if not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
        if len(raw) > max_bytes:
            raw = raw[-max_bytes:]
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _build_failure_dict(log_text: str) -> dict[str, Any]:
    try:
        from intelligent_platform.failure_parser import parse_failures

        rows = parse_failures(log_text)
        if rows:
            r = dict(rows[-1])
            r.setdefault("error_message", r.get("error_message", ""))
            r.setdefault("step_failed", r.get("step_failed", ""))
            return r
    except Exception:
        pass
    line = (log_text or "").strip().splitlines()
    last = line[-1] if line else ""
    return {
        "error_message": (log_text or "")[-4000:],
        "step_failed": last[:500],
    }


def analyze_failure_for_row(
    log_path: str | None,
    *,
    status: str = "",
    use_openrouter: bool = True,
) -> dict[str, Any]:
    """
    Return keys: failure_step, error_message, ai_failure_summary, root_cause_category,
    suggested_fix, ai_confidence, analysis_source, ai_status, model_used, key_present
    """
    meta = _read_build_ai_status_block()
    p = Path(log_path or "")
    log_text = _read_log_tail(p) if p else ""
    st = (status or "").upper()
    if st in ("PASS", "SKIPPED"):
        return {
            "failure_step": "",
            "error_message": "",
            "ai_failure_summary": "—",
            "root_cause_category": "—",
            "suggested_fix": "—",
            "ai_confidence": 1.0,
            "analysis_source": "N/A",
            "ai_status": meta.get("ai_status", "NOT_CHECKED"),
            "model_used": "—",
            "key_present": meta.get("key_present", "no"),
        }
    if st == "FLAKY":
        return {
            "failure_step": "—",
            "error_message": "—",
            "ai_failure_summary": "Flaky run — see log for first failure and retry context.",
            "root_cause_category": "Timing/Flaky Issue",
            "suggested_fix": "Stabilize waits; check device load and animation timing.",
            "ai_confidence": 0.55,
            "analysis_source": "Heuristic (FLAKY)",
            "ai_status": meta.get("ai_status", "NOT_CHECKED"),
            "model_used": "—",
            "key_present": meta.get("key_present", "no"),
        }

    fd = _build_failure_dict(log_text)
    err = (fd.get("error_message") or "")[:2000]
    step = (fd.get("step_failed") or err[:240] or "Unknown step")[:2000]

    has_key = bool(_read_openrouter_key())
    # OpenRouter is default: use when key is set and pre-flight did not set UNAVAILABLE.
    want_ai = use_openrouter and has_key and not _read_ai_status_unavailable()

    if want_ai:
        try:
            from intelligent_platform.ai_failure_analyzer import analyze_failure
            from intelligent_platform import config as _cfg

            if not _cfg.openrouter_configured():
                want_ai = False
            else:
                r = analyze_failure(fd)
                if r and str(r.get("root_cause", "")).strip():
                    asrc = str(
                        r.get("analysis_source")
                        or r.get("source_label")
                        or "OpenRouter"
                    )[:60]
                    return {
                        "failure_step": step,
                        "error_message": err
                        or str(r.get("root_cause", ""))[:2000],
                        "ai_failure_summary": str(r.get("root_cause", ""))[:2000],
                        "root_cause_category": str(
                            r.get("category", "assertion")
                        )[:120],
                        "suggested_fix": str(r.get("suggestion", ""))[:2000],
                        "ai_confidence": float(r.get("confidence", 0.7) or 0.7),
                        "analysis_source": asrc,
                        "ai_status": str(r.get("ai_status", meta.get("ai_status", "")) or "")
                        or meta.get("ai_status", "NOT_CHECKED")
                        or "",
                        "model_used": str(
                            r.get("model_used")
                            or meta.get("model_used_health", "")
                            or ""
                        )
                        or "—",
                        "key_present": "yes",
                    }
        except Exception as e:
            err = f"{err} [AI error: {e}]"[:2000] if err else f"AI error: {e}"

    # Rule-only
    r2 = _rule_fallback(err, step, log_text, meta=meta)
    r2["error_message"] = (err or r2.get("error_message", "See log."))[:2000]
    return r2


def _rule_fallback(
    err: str, step: str, log_text: str, *, meta: dict[str, str] | None = None
) -> dict[str, Any]:
    m = meta or _read_build_ai_status_block()
    text = f"{err} {log_text}"[-8000:]
    low = text.lower()
    base = {
        "key_present": m.get("key_present", "no"),
        "ai_status": m.get("ai_status", "NOT_CHECKED"),
    }
    if "device" in low and (
        "offline" in low or "unauthorized" in low or "not found" in low
    ):
        return {
            **base,
            "failure_step": step,
            "error_message": err or "Device / ADB issue",
            "ai_failure_summary": "ADB reports device not ready, offline, or unauthorized.",
            "root_cause_category": "Config/Setup Issue",
            "suggested_fix": "Check USB, authorize RSA, adb devices, and single concurrent user of adb.",
            "ai_confidence": 0.75,
            "analysis_source": "Rule-based fallback",
            "model_used": "rules",
        }
    if "element not found" in low or "id matching" in low:
        return {
            **base,
            "failure_step": step,
            "error_message": err or "Element not found",
            "ai_failure_summary": "Maestro could not find the target element (locator).",
            "root_cause_category": "locator",
            "suggested_fix": "Update selectors from hierarchy; add waits; check screen state.",
            "ai_confidence": 0.72,
            "analysis_source": "Rule-based fallback",
            "model_used": "rules",
        }
    if "assertion" in low:
        return {
            **base,
            "failure_step": step,
            "error_message": err or "Assertion failed",
            "ai_failure_summary": "Assertion did not pass within the test flow.",
            "root_cause_category": "assertion",
            "suggested_fix": "Compare expected vs app state; adjust timing and preconditions.",
            "ai_confidence": 0.6,
            "analysis_source": "Rule-based fallback",
            "model_used": "rules",
        }
    return {
        **base,
        "failure_step": step,
        "error_message": err or "Test failed — see log path.",
        "ai_failure_summary": (err or "Failure recorded; inspect log for the exact Maestro line.")[:2000],
        "root_cause_category": "Unknown",
        "suggested_fix": "Open the log file; reproduce locally with same device and data.",
        "ai_confidence": 0.45,
        "analysis_source": "Rule-based fallback",
        "model_used": "rules",
    }
