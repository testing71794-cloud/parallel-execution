"""
Send final_execution_report.xlsx after parallel orchestration completes.
Uses same env conventions as scripts/send_execution_email.py where possible.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("orch.mail")


def getenv_any(*names: str, default: str = "") -> str:
    for name in names:
        v = os.getenv(name, "").strip()
        if v:
            return v
    return default


def send_execution_report_email(
    excel_path: Path,
    *,
    subject: str | None = None,
    body: str | None = None,
) -> bool:
    """
    Returns True if mail was sent, False if skipped or failed (logged).
    """
    excel_path = excel_path.resolve()
    if not excel_path.is_file():
        logger.error("Excel attachment missing: %s", excel_path)
        return False

    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
    smtp_port_raw = getenv_any("SMTP_PORT", default="587")
    smtp_user = getenv_any("SMTP_USER", "SENDER_EMAIL")
    smtp_pass = getenv_any("SMTP_PASS", "SENDER_PASSWORD")
    sender = getenv_any("SENDER_EMAIL", "SMTP_USER")
    receiver = getenv_any("RECEIVER_EMAIL", "MAIL_TO")

    subj = subject or getenv_any(
        "ORCH_MAIL_SUBJECT", default="Automation Execution Report with AI Analysis"
    )
    text_body = body or (
        "Automation run finished.\n\n"
        f"Attached: {excel_path.name}\n"
    )

    if not smtp_server or not smtp_user or not smtp_pass or not receiver:
        logger.warning(
            "Email skipped: set SMTP_SERVER/SMTP_HOST, SMTP_USER, SMTP_PASS, RECEIVER_EMAIL/MAIL_TO"
        )
        return False

    try:
        port = int(smtp_port_raw)
    except ValueError:
        port = 587

    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = sender or smtp_user
    msg["To"] = receiver
    msg.set_content(text_body)
    msg.add_attachment(
        excel_path.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=excel_path.name,
    )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_server, port, timeout=60) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Email sent to %s", receiver)
        return True
    except Exception as e:
        logger.error("Email failed: %s", e)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(os.environ.get("WORKSPACE", os.getcwd())).resolve()
    excel = root / "final_execution_report.xlsx"
    if not excel.is_file():
        legacy = root / "build-summary" / "final_execution_report.xlsx"
        if legacy.is_file():
            excel = legacy
    return 0 if send_execution_report_email(excel) else 1


if __name__ == "__main__":
    raise SystemExit(main())
