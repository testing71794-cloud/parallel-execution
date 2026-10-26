"""
Normalize ATP status rows for reports.

Runner policy: final outcomes are PASS or FAIL only (never FLAKY). Soft successes
(recording teardown EOF, driver reinstall retry, etc.) keep a diagnostic reason
but must report as PASS and must not appear in Failed Tests.
"""
from __future__ import annotations

import re
from pathlib import Path

# Soft-success reasons written by run_one_flow_on_device.bat (status must be PASS).
SOFT_PASS_REASONS = frozenset(
    {
        "OK",
        "RECORDING_STOP_EOF_FLOW_OK",
        "MAESTRO_DRIVER_REINSTALL_OK",
        "MAESTRO_DEVICE_RETRY_OK",
        "MAESTRO_FAIL_REATTEMPT_OK",
        "SIGNUP_DUPLICATE_RETRY",
        "APPIUM_PINCH_OK",
    }
)

# Generic status-file reason codes — replace with Maestro log line when possible.
GENERIC_REASON_CODES = frozenset(
    {
        "",
        "—",
        "-",
        "MAESTRO_FAILED",
        "FAIL",
        "FLAKY",
        "ERROR",
        "PARSE_ERROR",
        "UNKNOWN",
    }
)

_LOG_REASON_PATTERNS = [
    re.compile(r"Assertion is false:.*", re.I),
    re.compile(r"Element not found:.*", re.I),
    re.compile(r"Unable to find element.*", re.I),
    re.compile(r"No visible element.*", re.I),
    re.compile(r"INSTALL_FAILED_[A-Z_]+.*", re.I),
    re.compile(r"Device .* is not connected.*", re.I),
    re.compile(r"Assertion failed.*", re.I),
    re.compile(r"TimeoutException:.*", re.I),
    re.compile(r"Timeout.*waiting.*", re.I),
    re.compile(r"FAILURE:.*", re.I),
    re.compile(r"Error:.*", re.I),
    re.compile(r"java\.lang\.[\w.]+Exception:.*", re.I),
]


def normalize_status(status: str, reason: str = "") -> str:
    """Map legacy FLAKY / soft-OK reasons to PASS or FAIL."""
    st = (status or "").strip().upper()
    reason_u = (reason or "").strip().upper()
    if reason_u in SOFT_PASS_REASONS:
        return "PASS"
    if st == "FLAKY":
        return "FAIL"
    if not st:
        return "UNKNOWN"
    return st


def is_soft_pass(status: str, reason: str = "") -> bool:
    return normalize_status(status, reason) == "PASS" and (
        (reason or "").strip().upper() in SOFT_PASS_REASONS
        or (status or "").strip().upper() == "PASS"
    )


def is_reportable_failure(status: str, reason: str = "") -> bool:
    """True when the row belongs in Failed Tests (excludes soft PASS)."""
    st = normalize_status(status, reason)
    return st in {"FAIL", "PARSE_ERROR", "ERROR"}


def reason_looks_generic(reason: str) -> bool:
    r = (reason or "").strip()
    if not r or r in GENERIC_REASON_CODES:
        return True
    return r.upper() in GENERIC_REASON_CODES


def extract_failure_reason_from_log(
    log_path: str | Path | None,
    fallback: str = "MAESTRO_FAILED",
    *,
    max_bytes: int = 200_000,
) -> str:
    """Best-effort Maestro assertion / error line from a flow log."""
    fb = (fallback or "").strip() or "MAESTRO_FAILED"
    p = Path(log_path) if log_path else None
    if not p or not p.is_file():
        return fb
    try:
        raw = p.read_bytes()
        if len(raw) > max_bytes:
            raw = raw[-max_bytes:]
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return fb

    # Prefer full Maestro assertion / element lines (clearer in the Failure Reason column).
    for pat in _LOG_REASON_PATTERNS:
        m = pat.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(0).strip())[:500]

    # Structured parser fallback.
    try:
        from intelligent_platform.failure_parser import parse_failures

        rows = parse_failures(text)
        if rows:
            err = str(rows[-1].get("error_message") or "").strip()
            step = str(rows[-1].get("step_failed") or "").strip()
            pick = err or step
            if pick and not reason_looks_generic(pick):
                return re.sub(r"\s+", " ", pick)[:500]
    except Exception:
        pass

    # "Final reason : ..." from bat — only if not a generic code.
    m_final = re.search(r"Final reason\s*:\s*(.+)", text, re.I)
    if m_final:
        fr = m_final.group(1).strip()
        if fr and not reason_looks_generic(fr):
            return fr[:500]

    for line in reversed(text.splitlines()):
        s = line.strip()
        if not s or s.startswith("["):
            continue
        low = s.lower()
        if any(
            k in low
            for k in ("assert", "element not found", "failed", "exception", "error:")
        ):
            return s[:500]
    return fb


def resolve_display_failure_reason(
    *,
    status: str = "",
    reason: str = "",
    log_path: str | Path | None = None,
    ai_analysis: str = "",
) -> str:
    """
    Failure Reason cell for reports: prefer Maestro log line over MAESTRO_FAILED /
    FLAKY codes. Soft-pass rows return empty (not shown in failed table).
    """
    if not is_reportable_failure(status, reason):
        return ""
    raw = (reason or "").strip()
    if raw and not reason_looks_generic(raw):
        # Keep informative status reasons (e.g. FLOW_FILE_NOT_FOUND, DEVICE_NOT_READY)
        if raw.upper() not in SOFT_PASS_REASONS:
            # Still try log for richer assertion text when reason is only a short code
            # of the MAESTRO_* family that isn't soft-pass.
            if raw.upper() in {"APPIUM_PINCH_FAILED", "FLOW_FILE_NOT_FOUND", "DEVICE_NOT_READY", "APP_NOT_INSTALLED"}:
                return raw
            # Non-generic free text already
            if " " in raw or len(raw) > 40:
                return raw[:500]

    from_log = extract_failure_reason_from_log(log_path, fallback="")
    if from_log and not reason_looks_generic(from_log):
        return from_log

    ai = (ai_analysis or "").strip()
    if ai and ai not in ("—", "-", "N/A") and "flaky run" not in ai.lower():
        if not reason_looks_generic(ai):
            return ai[:500]

    if raw and not reason_looks_generic(raw):
        return raw[:500]
    return from_log or raw or "MAESTRO_FAILED"
