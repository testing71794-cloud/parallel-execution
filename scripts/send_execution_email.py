#!/usr/bin/env python3
"""
Send Excel execution workbooks after ALL flows complete.
Set environment variables (same style as ai-doctor email):

  MAIL_TO          Recipient(s), comma-separated
  SMTP_HOST
  SMTP_PORT        (default 587)
  SMTP_USER
  SMTP_PASS
  SMTP_FROM        (optional; defaults to SMTP_USER)
  MAIL_SUBJECT     (optional)

If MAIL_TO is unset, exits 0 (no-op) so CI does not fail.
"""
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def main() -> int:
    to_raw = os.environ.get("MAIL_TO", "").strip()
    if not to_raw:
        print("MAIL_TO not set — skipping email (Excel files are in reports/excel/).")
        return 0

    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    if not host or not user:
        print("SMTP_HOST and SMTP_USER must be set to send email.", file=sys.stderr)
        return 1

    port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("SMTP_FROM", user).strip() or user
    subject = os.environ.get(
        "MAIL_SUBJECT",
        "Kodak Smile — Maestro execution Excel (all flows completed)",
    ).strip()

    root = Path(__file__).resolve().parent.parent
    excel_dir = root / "reports" / "excel"
    attachments = [
        excel_dir / "nonprinting_execution.xlsx",
        excel_dir / "printing_execution.xlsx",
    ]
    existing = [p for p in attachments if p.is_file()]
    if not existing:
        print("No Excel files found under reports/excel/ — nothing to attach.", file=sys.stderr)
        return 1

    body = """Hello,

All Maestro flows have finished. Attached:
- nonprinting_execution.xlsx (updated after each non-printing flow on all devices)
- printing_execution.xlsx (updated after each printing flow on all devices)

Regards,
Kodak Smile automation
"""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_raw
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in existing:
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)

    recipients = [a.strip() for a in to_raw.split(",") if a.strip()]

    try:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, recipients, msg.as_string())
    except Exception as exc:
        print(f"SMTP error: {exc}", file=sys.stderr)
        return 1

    print(f"Email sent to {to_raw} with {len(existing)} attachment(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
