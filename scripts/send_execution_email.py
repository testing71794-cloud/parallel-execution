#!/usr/bin/env python3
from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> int:
    smtp_server = env("SMTP_SERVER")
    smtp_port = int(env("SMTP_PORT", "587") or "587")
    sender_email = env("SENDER_EMAIL")
    sender_password = env("SENDER_PASSWORD")
    receiver_email = env("RECEIVER_EMAIL")

    if not all([smtp_server, sender_email, sender_password, receiver_email]):
        print("SMTP env vars not fully configured. Skipping email step.")
        return 0

    msg = EmailMessage()
    msg["Subject"] = env("EMAIL_SUBJECT", "Jenkins Execution Report")
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg.set_content("Execution completed. Please check the archived Jenkins reports and build summary.")

    summary_html = Path("build-summary") / "summary.html"
    if summary_html.exists():
        msg.add_alternative(summary_html.read_text(encoding="utf-8", errors="ignore"), subtype="html")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print("Email sent successfully.")
        return 0
    except Exception as exc:
        print(f"Email sending failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
