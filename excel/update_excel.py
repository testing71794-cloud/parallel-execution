"""
Thread-safe incremental updates to final_execution_report.xlsx.
Appends one row at a time; creates file with headers if missing.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

logger = logging.getLogger("orch.excel")

HEADERS = [
    "Timestamp",
    "Device Name",
    "Flow Name",
    "Test Status",
    "Failure Message",
    "AI Analysis",
    "Duration",
]

# Global re-entrancy guard for same-process nested calls (optional)
_file_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _meta_lock:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def append_result_row(
    excel_path: Path,
    row: dict[str, Any],
    *,
    file_lock: threading.Lock | None = None,
) -> None:
    """
    Append a single result row. Keys must match HEADERS (case-sensitive names).
    If file_lock is None, a per-file lock is used (thread-safe across workers).
    """
    excel_path = excel_path.resolve()
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    lock = file_lock or _lock_for(excel_path)
    values = [row.get(h, "") for h in HEADERS]

    with lock:
        if excel_path.is_file():
            wb = load_workbook(excel_path)
            ws = wb.active
            if ws.max_row == 0:
                ws.append(HEADERS)
                for c in ws[1]:
                    c.font = Font(bold=True)
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Results"
            ws.append(HEADERS)
            for c in ws[1]:
                c.font = Font(bold=True)

        ws.append(values)
        wb.save(excel_path)
        logger.info("Excel appended row: %s | %s", row.get("Flow Name"), row.get("Test Status"))


def finalize_workbook(excel_path: Path, *, file_lock: threading.Lock | None = None) -> None:
    """No-op placeholder if future validation/summary sheets are added."""
    excel_path = excel_path.resolve()
    if not excel_path.is_file():
        logger.warning("finalize: file missing %s", excel_path)
        return
    lock = file_lock or _lock_for(excel_path)
    with lock:
        wb = load_workbook(excel_path)
        wb.save(excel_path)
    logger.info("Excel finalized: %s", excel_path)
