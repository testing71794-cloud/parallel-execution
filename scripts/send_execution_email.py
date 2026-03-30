#!/usr/bin/env python3
"""
Send build summary email. Reads SMTP settings from the environment.

Required (any alias per row works):
  SMTP_SERVER or SMTP_HOST
  SENDER_EMAIL or SMTP_USER
  SENDER_PASSWORD or SMTP_PASS
  RECEIVER_EMAIL or MAIL_TO

Optional:
  SMTP_PORT (default 587 for STARTTLS, or 465 for SSL)
  SMTP_SSL=1          -> use SMTP_SSL on port 465 (Gmail / many providers)
  SMTP_USE_TLS=0      -> do not call STARTTLS after connect (rare)

If any required variable is missing, exits with code 1 so Jenkins shows a failure
instead of silently skipping (when you enabled Send Final Email).
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def truthy(name: str) -> bool:
    v = env(name).lower()
    return v in ("1", "true", "yes", "on")


def main() -> int:
    smtp_server = env("SMTP_SERVER") or env("SMTP_HOST")
    smtp_port_str = env("SMTP_PORT", "587") or "587"
    sender_email = env("SENDER_EMAIL") or env("SMTP_USER")
    sender_password = env("SENDER_PASSWORD") or env("SMTP_PASS")
    receiver_email = env("RECEIVER_EMAIL") or env("MAIL_TO")

    def report_missing() -> None:
        checks = [
            ("SMTP_SERVER or SMTP_HOST", smtp_server),
            ("SENDER_EMAIL or SMTP_USER", sender_email),
            ("SENDER_PASSWORD or SMTP_PASS", sender_password),
            ("RECEIVER_EMAIL or MAIL_TO", receiver_email),
        ]
        print("=== Email configuration check (Jenkins agent must define these) ===")
        for label, val in checks:
            print(f"  {label}: {'SET' if val else 'MISSING'}")
        print()
        print(
            "Add them on the Windows agent that runs the job, for example:\n"
            "  Jenkins → Manage Jenkins → Nodes → <your agent> → Configure → Environment variables\n"
            "or: Job → Configure → Build Environment → Inject environment variables\n"
            "or: wrap with Credentials Binding (secret text) mapped to SENDER_PASSWORD."
        )

    if not all([smtp_server, sender_email, sender_password, receiver_email]):
        report_missing()
        print("ERROR: Email not sent — SMTP environment incomplete. See messages above.")
        return 1

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        print(f"ERROR: SMTP_PORT must be a number, got: {smtp_port_str!r}")
        return 1

    use_ssl = truthy("SMTP_SSL") or smtp_port == 465

    msg = EmailMessage()
    msg["Subject"] = env("EMAIL_SUBJECT", "Jenkins Execution Report")
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.set_content("Execution completed. See attached workbooks and the archived Jenkins artifacts.")

    summary_html = Path("build-summary") / "summary.html"
    if summary_html.exists():
        msg.add_alternative(summary_html.read_text(encoding="utf-8", errors="ignore"), subtype="html")

    for attach in (
        Path("reports") / "nonprinting_summary" / "summary.xlsx",
        Path("reports") / "printing_summary" / "summary.xlsx",
        Path("build-summary") / "final_execution_report.xlsx",
    ):
        if attach.is_file():
            msg.add_attachment(
                attach.read_bytes(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=attach.name,
            )

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                tls_off = env("SMTP_USE_TLS", "1").lower() in ("0", "false", "no", "off")
                if not tls_off:
                    server.starttls(context=ssl.create_default_context())
                server.login(sender_email, sender_password)
                server.send_message(msg)
        print(f"Email sent successfully to {receiver_email} via {smtp_server}:{smtp_port} (ssl={use_ssl}).")
        return 0
    except Exception as exc:
        print(f"ERROR: Email send failed ({type(exc).__name__}): {exc}")
        print(
            "Hints: Gmail needs an App Password (not your normal password), "
            "and often SMTP_SSL=1 SMTP_PORT=465 or SMTP_PORT=587 with STARTTLS."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
