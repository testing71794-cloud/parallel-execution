#!/usr/bin/env python3
import json
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def load_summary(root: Path):
    path = root / 'build-summary' / 'summary.json'
    if not path.exists():
        return {'total': 0, 'passed': 0, 'failed': 0, 'rows': []}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'total': 0, 'passed': 0, 'failed': 0, 'rows': []}


def pick_attachments(root: Path):
    candidates = [
        root / 'build-summary' / 'final_execution_report.xlsx',
        root / 'reports' / 'nonprinting_summary' / 'summary.xlsx',
        root / 'reports' / 'printing_summary' / 'summary.xlsx',
        root / 'build-summary' / 'summary.html',
        root / 'ai-doctor' / 'artifacts' / 'cursor-report.md',
        root / 'ai-doctor' / 'artifacts' / 'ai-report.json',
        root / 'ai-doctor' / 'artifacts' / 'maestro_stdout.log',
        root / 'ai-doctor' / 'artifacts' / 'maestro_stderr.log',
    ]
    return [p for p in candidates if p.exists() and p.is_file()]


def build_body(summary):
    failed = [r for r in summary.get('rows', []) if r.get('status') == 'FAIL']
    body = [
        'Hello,',
        '',
        'The Kodak Smile Jenkins execution has finished.',
        '',
        f"Total results: {summary.get('total', 0)}",
        f"Passed: {summary.get('passed', 0)}",
        f"Failed: {summary.get('failed', 0)}",
        '',
        'Attached files include:',
        '- Final execution workbook with Summary, All Results, Failed Flows, and Passed Flows',
        '- Non-printing suite Excel summary',
        '- Printing suite Excel summary',
        '- HTML build summary',
        '- AI analysis artifacts when generated',
        '',
    ]
    if failed:
        body.append('Failed flow results:')
        for row in failed[:50]:
            body.append(f"- {row.get('suite')} | {row.get('flow')} | {row.get('device')}")
        if len(failed) > 50:
            body.append(f"- ... and {len(failed)-50} more")
        body.append('')
    else:
        body.append('No failed flow results were found.')
        body.append('')
    body.append('Regards,')
    body.append('Kodak Smile automation')
    return '\n'.join(body)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    to_raw = os.environ.get('MAIL_TO', '').strip()
    if not to_raw:
        print('MAIL_TO not set. Skipping end-of-run email.')
        return 0

    host = os.environ.get('SMTP_HOST', '').strip()
    user = os.environ.get('SMTP_USER', '').strip()
    password = os.environ.get('SMTP_PASS', '').strip()
    if not host or not user:
        print('SMTP_HOST and SMTP_USER must be set to send email.', file=sys.stderr)
        return 1

    port = int(os.environ.get('SMTP_PORT', '587'))
    from_addr = os.environ.get('SMTP_FROM', user).strip() or user
    summary = load_summary(root)
    subject = os.environ.get('MAIL_SUBJECT', '').strip() or (
        f"Kodak Smile Automation Result | Passed {summary.get('passed', 0)} | Failed {summary.get('failed', 0)}"
    )

    attachments = pick_attachments(root)
    if not attachments:
        print('No attachments found. Email will still be sent without attachments.')

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_raw
    msg.attach(MIMEText(build_body(summary), 'plain', 'utf-8'))

    for path in attachments:
        with open(path, 'rb') as f:
            part = MIMEApplication(f.read(), Name=path.name)
            part['Content-Disposition'] = f'attachment; filename="{path.name}"'
            msg.attach(part)

    recipients = [a.strip() for a in to_raw.split(',') if a.strip()]
    try:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, recipients, msg.as_string())
    except Exception as exc:
        print(f'SMTP error: {exc}', file=sys.stderr)
        return 1

    print(f'Email sent to {to_raw} with {len(attachments)} attachment(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
