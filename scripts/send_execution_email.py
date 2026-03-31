from __future__ import annotations

import os
import smtplib
import ssl
import zipfile
from email.message import EmailMessage
from pathlib import Path

WORKSPACE = Path(r"C:\JenkinsAgent\workspace\Kodak-smile-automation")
REPORTS_DIR = WORKSPACE / "reports"
BUILD_SUMMARY_DIR = WORKSPACE / "build-summary"
LOGS_ZIP = BUILD_SUMMARY_DIR / "execution_logs.zip"


def getenv_any(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def truthy_env(name: str, default: str = "0") -> bool:
    return getenv_any(name, default=default).lower() in {"1", "true", "yes", "on"}


def collect_excel_attachments() -> list[Path]:
    candidates = [
        BUILD_SUMMARY_DIR / "final_execution_report.xlsx",
        REPORTS_DIR / "nonprinting_summary.xlsx",
        REPORTS_DIR / "printing_summary.xlsx",
        REPORTS_DIR / "nonprinting" / "summary.xlsx",
        REPORTS_DIR / "printing" / "summary.xlsx",
    ]
    seen = set()
    output = []
    for path in candidates:
        if path.exists() and path not in seen:
            seen.add(path)
            output.append(path)
    return output


def collect_log_files() -> list[Path]:
    if not REPORTS_DIR.exists():
        return []
    return sorted(p for p in REPORTS_DIR.glob("**/*.log") if p.is_file())


def build_logs_zip(log_files: list[Path]) -> Path | None:
    if not log_files:
        return None
    BUILD_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(LOGS_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in log_files:
            try:
                arcname = file_path.relative_to(WORKSPACE)
            except ValueError:
                arcname = file_path.name
            zf.write(file_path, arcname=str(arcname))
    return LOGS_ZIP


def load_failed_summary() -> str:
    failed_summary = BUILD_SUMMARY_DIR / "failed_summary.txt"
    if failed_summary.exists():
        return failed_summary.read_text(encoding="utf-8", errors="ignore").strip()
    return "Failed summary not available."


def main() -> int:
    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
    smtp_port_raw = getenv_any("SMTP_PORT", default="587")
    smtp_user = getenv_any("SMTP_USER", "SENDER_EMAIL")
    smtp_pass = getenv_any("SMTP_PASS", "SENDER_PASSWORD")
    sender = getenv_any("SENDER_EMAIL", "SMTP_USER")
    receiver = getenv_any("RECEIVER_EMAIL", "MAIL_TO")

    print("=== Email configuration check ===")
    print(f"SMTP server : {'OK' if smtp_server else 'MISSING'}")
    print(f"SMTP user   : {'OK' if smtp_user else 'MISSING'}")
    print(f"SMTP pass   : {'OK' if smtp_pass else 'MISSING'}")
    print(f"Receiver    : {'OK' if receiver else 'MISSING'}")

    missing = []
    if not smtp_server:
        missing.append("SMTP_SERVER/SMTP_HOST")
    if not smtp_user:
        missing.append("SMTP_USER/SENDER_EMAIL")
    if not smtp_pass:
        missing.append("SMTP_PASS/SENDER_PASSWORD")
    if not receiver:
        missing.append("RECEIVER_EMAIL/MAIL_TO")

    if missing:
        print("Missing required environment variables:")
        for item in missing:
            print(f" - {item}")
        return 1

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        print(f"Invalid SMTP_PORT: {smtp_port_raw}")
        return 1

    excel_attachments = collect_excel_attachments()
    log_files = collect_log_files()
    logs_zip = build_logs_zip(log_files)
    failed_summary = load_failed_summary()

    msg = EmailMessage()
    msg["Subject"] = getenv_any("EMAIL_SUBJECT", default="Jenkins Execution Report")
    msg["From"] = sender
    msg["To"] = receiver

    body_lines = [
        "Hello,",
        "",
        "Please find the latest Jenkins execution report attached.",
        "",
        "Failed flow summary:",
        failed_summary,
        "",
        "Attached files:",
    ]

    if excel_attachments:
        for file in excel_attachments:
            body_lines.append(f" - {file.name}")
    else:
        body_lines.append(" - No Excel attachment found")

    if logs_zip:
        body_lines.append(f" - {logs_zip.name}")
    else:
        body_lines.append(" - No log files found")

    body_lines += ["", "Regards,", "Jenkins Automation"]
    msg.set_content("\n".join(body_lines))

    summary_html = BUILD_SUMMARY_DIR / "summary.html"
    if summary_html.exists():
        msg.add_alternative(summary_html.read_text(encoding="utf-8", errors="ignore"), subtype="html")

    for file_path in excel_attachments:
        msg.add_attachment(
            file_path.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=file_path.name,
        )
        print(f"Attached Excel: {file_path}")

    if logs_zip and logs_zip.exists():
        msg.add_attachment(
            logs_zip.read_bytes(),
            maintype="application",
            subtype="zip",
            filename=logs_zip.name,
        )
        print(f"Attached Logs Zip: {logs_zip}")

    try:
        if truthy_env("SMTP_SSL") or smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=ssl.create_default_context()) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                if truthy_env("SMTP_USE_TLS", default="1"):
                    context = ssl._create_unverified_context()  # ✅ FIX HERE
                    server.starttls(context=context)
                    server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return 1

    print("Email sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())