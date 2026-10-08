#!/usr/bin/env python3
"""
Send a one-off demo email with final_execution_report.xlsx attached.

Does NOT commit. Requires SMTP env (same names as Jenkins / mailout/send_email.py):

  set SMTP_SERVER=smtp.gmail.com
  set SMTP_PORT=587
  set SMTP_USER=your@gmail.com
  set SMTP_PASS=your-app-password
  set RECEIVER_EMAIL=your@gmail.com
  set ORCH_MAIL_SUBJECT=DEMO Kodak Smile Excel attachment

  python scripts/send_demo_execution_email.py
  python scripts/send_demo_execution_email.py path\\to\\final_execution_report.xlsx
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mailout.send_email import (  # noqa: E402
    resolve_final_excel_path,
    send_execution_report_email,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) > 1:
        excel = Path(sys.argv[1]).resolve()
    else:
        found = resolve_final_excel_path(REPO)
        excel = found if found is not None else (REPO / "build-summary" / "final_execution_report.xlsx")

    if not excel.is_file():
        print(f"ERROR: Excel not found: {excel}", file=sys.stderr)
        return 1

    os.environ.setdefault(
        "ORCH_MAIL_SUBJECT",
        "DEMO — Kodak Smile final_execution_report.xlsx attachment check",
    )
    print(f"Excel: {excel} ({excel.stat().st_size} bytes)")
    print(f"To: {os.environ.get('RECEIVER_EMAIL') or os.environ.get('MAIL_TO') or '(unset)'}")
    ok = send_execution_report_email(excel, root=REPO)
    if ok:
        print("OK: demo email sent with Excel attached.")
        return 0
    print("FAILED: demo email not sent (check SMTP_* / RECEIVER_EMAIL).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
