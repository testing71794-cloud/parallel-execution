#!/usr/bin/env python3
"""
Build the same HTML body as mailout/send_email.py and write email_preview.html
so you can open it in a browser. Does not send email.

Usage:
  python scripts/preview_execution_email_html.py
  python scripts/preview_execution_email_html.py build-summary\\final_execution_report.xlsx
  python scripts/preview_execution_email_html.py C:\\path\\to\\final_execution_report.xlsx
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mailout.send_email import (  # noqa: E402
    build_email_html,
    build_summary_display_pairs,
    read_execution_table_rows,
    read_summary_sheet_key_values,
    resolve_final_excel_path,
)


def main() -> int:
    if len(sys.argv) > 1:
        xlsx = Path(sys.argv[1]).resolve()
    else:
        xlsx = resolve_final_excel_path(REPO) or (REPO / "build-summary" / "final_execution_report.xlsx")

    out: Path
    if xlsx.is_file():
        rows, err = read_execution_table_rows(xlsx)
        out = xlsx.parent / "email_preview.html"
        print(f"Source: {xlsx}")
    else:
        print(f"[WARN] Excel not found: {xlsx}")
        print("Showing empty-table preview. Pass a path: python scripts/preview_execution_email_html.py <file.xlsx>")
        rows, err = [], f"File not found: {xlsx}"
        out = REPO / "build-summary" / "email_preview.html"
        out.parent.mkdir(parents=True, exist_ok=True)

    gen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_kv = read_summary_sheet_key_values(xlsx) if xlsx.is_file() else {}
    summary_pairs = build_summary_display_pairs(sheet_kv, rows, gen)
    att = ["final_execution_report.xlsx", "execution_logs.zip (execution logs)"]
    html = build_email_html(rows, gen, err, att, summary_pairs)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote: {out}")
    print("Open in browser: file:///" + str(out).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
