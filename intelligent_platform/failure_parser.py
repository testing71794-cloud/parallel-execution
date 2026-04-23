"""
Extract structured failure data from Maestro/JUnit logs and status files.
Output is JSON-friendly dicts only (no ad-hoc string passing between stages).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Maestro / Android common patterns (tolerant to noise)
_STEP_PATTERNS = [
    re.compile(r"Running flow:\s*(.+)", re.I),
    re.compile(r"====\s*RUN SHARD-ALL[^\n]*\n.*?Flow name\s*:\s*(.+)", re.S | re.I),
    re.compile(r"Flow name\s*:\s*(.+)", re.I),
]
AssertionLine = re.compile(
    r"Assertion is false:\s*(.+?)(?:\n|$)", re.I | re.S
)
_ELEMENT_FAIL = re.compile(
    r"(element not found|could not find element|id matching regex)[^\n]*\n?([^\n]{0,400})",
    re.I,
)
_CRASH = re.compile(r"(java\.lang\.[\w.]+|FATAL EXCEPTION|AndroidRuntime)", re.I)
_SCREEN_HINT = re.compile(
    r"(?:screen|activity|window)[^\n]{0,3}[:=]\s*([^\n]+)", re.I
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_failures(log_text: str) -> list[dict[str, Any]]:
    """
    Extract structured rows from arbitrary log text (no file I/O).
    Handles noisy logs, partial Maestro output, inconsistent formats.
    """
    text = log_text or ""
    if not text.strip():
        return []

    blocks = re.split(r"(?:^|\n)(?=={3,}|Running flow:)", text)
    out: list[dict[str, Any]] = []
    for chunk in blocks:
        row = _parse_log_block(chunk.strip())
        if row and (row.get("error_message") or row.get("step_failed")):
            out.append(row)
    if not out and text.strip():
        row = _parse_log_block(text)
        if row:
            out.append(row)
    return out


def _parse_log_block(chunk: str) -> dict[str, Any] | None:
    if not chunk.strip():
        return None

    test_name = "unknown_flow"
    for pat in _STEP_PATTERNS:
        m = pat.search(chunk)
        if m:
            test_name = m.group(1).strip().splitlines()[0].strip()[:200]
            break

    err = ""
    if _CRASH.search(chunk):
        err = _CRASH.search(chunk).group(0)  # type: ignore[union-attr]
        mlines = [ln for ln in chunk.splitlines() if "AndroidRuntime" in ln or "Caused by" in ln]
        if mlines:
            err = (err + "\n" + "\n".join(mlines[:5]))[:2000]
    elif _ELEMENT_FAIL.search(chunk):
        g = _ELEMENT_FAIL.search(chunk)
        err = f"{g.group(1)}: {g.group(2)[:500]}"  # type: ignore[union-attr]
    elif AssertionLine.search(chunk):
        err = AssertionLine.search(chunk).group(1).strip()[:2000]  # type: ignore[union-attr]
    else:
        # last resort: last non-empty error-ish line
        for ln in reversed(chunk.splitlines()):
            if any(
                k in ln.lower()
                for k in ("error", "failed", "assertion", "false", "exception")
            ):
                err = ln.strip()[:2000]
                break

    screen = ""
    sm = _SCREEN_HINT.search(chunk)
    if sm:
        screen = sm.group(1).strip()[:300]

    step_failed = ""
    for ln in chunk.splitlines():
        if "assert" in ln.lower() or "tap" in ln.lower() or "runFlow" in ln:
            step_failed = ln.strip()[:500]
            break

    action = "unknown"
    low = chunk.lower()
    if "tap" in low:
        action = "tap"
    elif "assert" in low:
        action = "assert"
    elif "runflow" in low or "run flow" in low:
        action = "runFlow"
    elif "input" in low or "text" in low:
        action = "input"

    return {
        "test_name": test_name,
        "step_failed": step_failed or err[:300] or "unknown_step",
        "action": action,
        "screen": screen or _infer_screen(err, test_name),
        "error_message": err or chunk[-1500:].strip(),
        "timestamp": _now_iso(),
        "suite": "",
        "flow": test_name,
        "device": "",
        "source": "log_text",
        "raw_log_excerpt": chunk[:8000],
    }


def _norm_err(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s)
    return s[:200]


def _infer_screen(err: str, test_name: str) -> str:
    e, t = (err or "").lower(), (test_name or "").lower()
    if "print" in e or "print" in t:
        return "printing"
    if "login" in e or "login" in t:
        return "login"
    if "home" in e or "kodak" in e:
        return "home"
    if "bluetooth" in e or "pair" in e:
        return "pairing"
    return "unknown"


def _parse_status_line_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return data


def _failure_score(text: str) -> int:
    t = (text or "").lower()
    score = 0
    for kw in (
        "element not found",
        "assertion",
        "failed",
        "error",
        "exception",
        "crash",
        "regex",
        "tap",
    ):
        if kw in t:
            score += 5
    score += min(len(t), 2000) // 100
    return score


def _merge_parsed_blocks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """When a log yields multiple blocks, keep the block that looks most like the real failure."""
    if len(rows) <= 1:
        return rows
    best = max(
        rows,
        key=lambda r: _failure_score(
            str(r.get("error_message", "")) + str(r.get("raw_log_excerpt", ""))
        ),
    )
    return [best]


def parse_junit_file(path: Path) -> list[dict[str, Any]]:
    """Parse JUnit XML into structured failures (failed / error testcases)."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return out

    for case in root.iter("testcase"):
        name = case.get("name") or "unknown"
        classname = case.get("classname") or ""
        t = case.get("time") or ""
        fail = case.find("failure")
        err_el = case.find("error")
        node = fail if fail is not None else err_el
        if node is None:
            continue
        msg = node.get("message") or ""
        body = (node.text or "").strip()
        out.append(
            {
                "test_name": f"{classname} :: {name}".strip(" :") or name,
                "step_failed": (msg or body)[:500],
                "action": "assert" if "assert" in (msg + body).lower() else "unknown",
                "screen": _infer_screen(msg + body, name),
                "error_message": f"{msg}\n{body}"[:4000].strip(),
                "timestamp": _now_iso(),
                "suite": "",
                "flow": name,
                "device": "",
                "source": "junit",
                "raw_log_excerpt": f"{path}: {name}",
            }
        )
    return out


def collect_failures_from_workspace(root: Path) -> list[dict[str, Any]]:
    """
    Discover failures from:
    - status/*.txt (FAIL / non-PASS) + linked .log
    - any report.xml / *junit*.xml under root
    """
    root = root.resolve()
    results: list[dict[str, Any]] = []
    status_dir = root / "status"
    if status_dir.is_dir():
        for p in sorted(status_dir.glob("*.txt")):
            data = _parse_status_line_file(p)
            st = (data.get("status") or "").upper()
            if st in ("", "RUNNING", "PASS"):
                continue
            log_path = Path(data.get("log", "") or "")
            log_text = ""
            if log_path.is_absolute() and log_path.is_file():
                log_text = log_path.read_text(encoding="utf-8", errors="ignore")
            elif (root / log_path).is_file():
                log_text = (root / log_path).read_text(encoding="utf-8", errors="ignore")
            elif log_path.name and (status_dir / log_path.name).is_file():
                log_text = (status_dir / log_path.name).read_text(
                    encoding="utf-8", errors="ignore"
                )

            parsed = parse_failures(log_text) if log_text else []
            if parsed:
                # One status file should map to one primary failure row; merge split blocks
                merged = _merge_parsed_blocks(parsed)
                for row in merged:
                    row["suite"] = data.get("suite", "")
                    row["flow"] = data.get("flow", row.get("flow", ""))
                    row["device"] = data.get("device", "")
                    row["source"] = "status+log"
                    results.append(row)
            else:
                results.append(
                    {
                        "test_name": data.get("flow", p.stem),
                        "step_failed": data.get("status", "FAIL"),
                        "action": "unknown",
                        "screen": "unknown",
                        "error_message": f"Status file indicates failure. log={data.get('log', '')}",
                        "timestamp": _now_iso(),
                        "suite": data.get("suite", ""),
                        "flow": data.get("flow", ""),
                        "device": data.get("device", ""),
                        "source": "status_only",
                        "raw_log_excerpt": log_text[:8000] if log_text else "",
                    }
                )

    # JUnit: root and common report locations
    candidates = [root / "report.xml", root / "report_retry.xml"]
    for pattern in ("**/junit.xml", "**/*junit*.xml", "**/report.xml", "**/TEST-*.xml"):
        for p in root.glob(pattern):
            if p.is_file() and p not in candidates:
                candidates.append(p)
    seen: set[Path] = set()
    for jpath in candidates:
        if not jpath.is_file() or jpath in seen:
            continue
        seen.add(jpath)
        for row in parse_junit_file(jpath):
            row["source"] = f"junit:{jpath.name}"
            results.append(row)

    # De-dupe: suite + flow + device + normalized error fragment
    def _dk(r: dict[str, Any]) -> tuple:
        ne = _norm_err(str(r.get("error_message", "")))
        return (
            str(r.get("suite", "")),
            str(r.get("flow", "")),
            str(r.get("device", "")),
            ne,
        )

    deduped: dict[tuple, dict[str, Any]] = {}
    for r in results:
        k = _dk(r)
        prev = deduped.get(k)
        if prev is None or len(str(r.get("error_message", ""))) > len(
            str(prev.get("error_message", ""))
        ):
            deduped[k] = r
    return list(deduped.values())
