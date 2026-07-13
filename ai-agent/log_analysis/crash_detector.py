"""Crash / ANR / OOM / Bluetooth / printer signal detection from logcat text."""

from __future__ import annotations

import re
from dataclasses import dataclass


CRASH_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fatal_exception", re.compile(r"FATAL EXCEPTION", re.I)),
    ("anr", re.compile(r"ANR in |Application Not Responding", re.I)),
    ("oom", re.compile(r"OutOfMemoryError|lowmemorykiller", re.I)),
    ("native_crash", re.compile(r"Fatal signal|DEBUG\s*:\s*\*\*\* \*\*\* \*\*\*", re.I)),
    ("bluetooth", re.compile(r"Bluetooth.*(fail|error|timeout)|bt_stack", re.I)),
    ("printer", re.compile(r"printer.*(fail|error|timeout|disconnect)|zink|kodak.*print", re.I)),
]


@dataclass(frozen=True)
class CrashFinding:
    kind: str
    line: str


class CrashDetector:
    def analyze(self, log_text: str, *, max_hits: int = 50) -> list[CrashFinding]:
        findings: list[CrashFinding] = []
        for line in (log_text or "").splitlines():
            for kind, pat in CRASH_PATTERNS:
                if pat.search(line):
                    findings.append(CrashFinding(kind=kind, line=line.strip()[:400]))
                    break
            if len(findings) >= max_hits:
                break
        return findings

    def summarize(self, findings: list[CrashFinding]) -> list[str]:
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        return [f"{k}:{v}" for k, v in sorted(counts.items())]
