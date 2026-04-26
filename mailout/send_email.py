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


def resolve_final_excel_path(root: Path) -> Path | None:
    """
    Locate final_execution_report.xlsx for attachment.
    Order: explicit env path → repo root → build-summary → shallowest rglob under root.
    """
    root = root.resolve()
    for env_name in ("FINAL_EXECUTION_REPORT_XLSX", "ORCH_EXCEL_OUT"):
        raw = os.getenv(env_name, "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = (root / p).resolve()
        if p.is_file():
            logger.info("Using Excel from %s=%s", env_name, p)
            return p
        logger.warning("Env %s points to missing file: %s", env_name, p)

    candidates = [
        root / "final_execution_report.xlsx",
        root / "build-summary" / "final_execution_report.xlsx",
    ]
    for c in candidates:
        if c.is_file():
            logger.info("Using Excel: %s", c)
            return c

    matches = [p for p in root.rglob("final_execution_report.xlsx") if p.is_file()]
    if matches:
        best = min(matches, key=lambda p: (len(p.parts), str(p)))
        logger.info("Using Excel (search): %s", best)
        return best

    logger.error(
        "No final_execution_report.xlsx under %s (tried env FINAL_EXECUTION_REPORT_XLSX / ORCH_EXCEL_OUT, root, build-summary, rglob)",
        root,
    )
    return None


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

    smtp_user = getenv_any("SMTP_USER", "SENDER_EMAIL", "GMAIL_USER")
    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
    # Gmail: if user set but host missing, use standard Gmail SMTP (app password in SMTP_PASS).
    if not smtp_server and smtp_user and "@" in smtp_user and smtp_user.lower().rstrip().endswith(
        ("@gmail.com", "@googlemail.com")
    ):
        smtp_server = "smtp.gmail.com"
        logger.info("Defaulting SMTP server to smtp.gmail.com (Gmail sender)")

    smtp_port_raw = getenv_any("SMTP_PORT", default="587")
    smtp_pass = getenv_any(
        "SMTP_PASS",
        "SMTP_PASSWORD",
        "SENDER_PASSWORD",
        "GMAIL_APP_PASSWORD",
    )
    sender = getenv_any("SENDER_EMAIL", "SMTP_USER", "GMAIL_USER")
    receiver = getenv_any(
        "RECEIVER_EMAIL",
        "MAIL_TO",
        "EMAIL_RECIPIENTS",
        "RECIPIENT",
        "ORCH_MAIL_TO",
    )

    subj = subject or getenv_any(
        "ORCH_MAIL_SUBJECT", default="Automation Execution Report with AI Analysis"
    )
    text_body = body or (
        "Automation run finished.\n\n"
        f"Attached: {excel_path.name}\n"
    )

    if not smtp_server or not smtp_user or not smtp_pass or not receiver:
        logger.warning(
            "Email skipped: set at minimum SMTP_USER (or SENDER_EMAIL), "
            "SMTP_PASS (or SMTP_PASSWORD), RECEIVER_EMAIL (or MAIL_TO), and "
            "SMTP_SERVER (or omit for @gmail.com to default to smtp.gmail.com). "
            "Gmail: use an App Password, not the normal account password."
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
    excel = resolve_final_excel_path(root)
    if excel is None:
        return 1
    return 0 if send_execution_report_email(excel) else 1


if __name__ == "__main__":
    raise SystemExit(main())
