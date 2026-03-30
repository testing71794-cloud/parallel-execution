#!/usr/bin/env python3
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


def report_missing(smtp_server, sender_email, sender_password, receiver_email):
    print("=== Email configuration check (Jenkins agent must define these) ===")
    print(f"  SMTP_SERVER or SMTP_HOST: {'SET' if smtp_server else 'MISSING'}")
    print(f"  SENDER_EMAIL or SMTP_USER: {'SET' if sender_email else 'MISSING'}")
    print(f"  SENDER_PASSWORD or SMTP_PASS: {'SET' if sender_password else 'MISSING'}")
    print(f"  RECEIVER_EMAIL or MAIL_TO: {'SET' if receiver_email else 'MISSING'}")
    print()
    print(
        "Add them on the Windows agent that runs the job, for example:\n"
        "  set SMTP_SERVER=smtp.gmail.com\n"
        "  set SMTP_PORT=587\n"
        "  set SENDER_EMAIL=your_email@gmail.com\n"
        "  set SENDER_PASSWORD=your_app_password\n"
        "  set RECEIVER_EMAIL=your_email@gmail.com\n"
        "or configure in Jenkins Environment Variables or Credentials Binding."
    )


def main() -> int:
    smtp_server = env("SMTP_SERVER") or env("SMTP_HOST")
    smtp_port_str = env("SMTP_PORT", "587") or "587"
    sender_email = env("SENDER_EMAIL") or env("SMTP_USER")
    sender_password = env("SENDER_PASSWORD") or env("SMTP_PASS")
    receiver_email = env("RECEIVER_EMAIL") or env("MAIL_TO")

    if not all([smtp_server, sender_email, sender_password, receiver_email]):
        report_missing(smtp_server, sender_email, sender_password, receiver_email)
        print("ERROR: Email not sent — SMTP environment incomplete.")
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
    msg.set_content("Execution completed. See attached reports.")

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
                if env("SMTP_USE_TLS", "1").lower() not in ("0", "false", "no"):
                    server.starttls(context=ssl.create_default_context())
                server.login(sender_email, sender_password)
                server.send_message(msg)

        print(f"Email sent successfully to {receiver_email}")
        return 0

    except Exception as exc:
        print(f"ERROR: Email send failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())