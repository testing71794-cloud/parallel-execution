import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

WORKSPACE = Path(r"C:\JenkinsAgent\workspace\Kodak-smile-automation")

def getenv_any(*names, default=""):
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default

def collect_attachments():
    candidates = [
        WORKSPACE / "build-summary" / "final_execution_report.xlsx",
        WORKSPACE / "reports" / "nonprinting_summary.xlsx",
        WORKSPACE / "reports" / "printing_summary.xlsx",
    ]
    return [p for p in candidates if p.exists()]

def main():
    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
    smtp_port = int(getenv_any("SMTP_PORT", default="587"))
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

    attachments = collect_attachments()

    msg = EmailMessage()
    msg["Subject"] = "Jenkins Execution Report"
    msg["From"] = sender
    msg["To"] = receiver

    body_lines = [
        "Hello,",
        "",
        "Please find the latest Jenkins execution report attached.",
        "",
        "Attached files:",
    ]

    if attachments:
        for file in attachments:
            body_lines.append(f" - {file.name}")
    else:
        body_lines.append(" - No Excel attachment found")

    body_lines += [
        "",
        "Regards,",
        "Jenkins Automation",
    ]

    msg.set_content("\n".join(body_lines))

    for file_path in attachments:
        with open(file_path, "rb") as f:
            data = f.read()
        msg.add_attachment(
            data,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=file_path.name,
        )
        print(f"Attached: {file_path}")

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print("Email sent successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())