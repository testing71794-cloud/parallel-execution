"""
Send final_execution_report.xlsx after parallel orchestration completes.
Uses same env conventions as scripts/send_execution_email.py where possible.
"""
from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from openpyxl import load_workbook

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


def resolve_execution_logs_zip(excel_path: Path, root: Path | None) -> Path | None:
    """Attach build-summary/execution_logs.zip (or next to the Excel) when present."""
    candidates: list[Path] = [excel_path.parent / "execution_logs.zip"]
    if root is not None:
        r = root.resolve()
        candidates.extend(
            [
                r / "build-summary" / "execution_logs.zip",
                r / "execution_logs.zip",
            ]
        )
    seen: set[Path] = set()
    for p in candidates:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        if rp.is_file():
            logger.info("Found execution logs zip: %s", rp)
            return rp
    return None


def _select_data_sheet(wb) -> object | None:
    if "Raw Results" in wb.sheetnames:
        return wb["Raw Results"]
    for name in wb.sheetnames:
        ws = wb[name]
        row1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not row1:
            continue
        headers = [str(h or "").strip() for h in row1]
        if "Status" not in headers:
            continue
        if "Suite" in headers or "Flow Name" in headers or "Flow" in headers:
            return ws
    return None


def _col_index(headers: list[str], *candidates: str) -> int | None:
    lower = {h.strip().lower(): i for i, h in enumerate(headers) if h and str(h).strip()}
    for c in candidates:
        key = c.strip().lower()
        if key in lower:
            return lower[key]
    return None


def read_execution_table_rows(
    excel_path: Path,
) -> tuple[list[dict[str, str]], str | None]:
    """
    Return rows for Suite, Flow, Device, Status, Exit Code from the workbook
    and an optional error/warning message.
    """
    path = excel_path.resolve()
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = _select_data_sheet(wb)
        if ws is None:
            return [], "No tabular sheet found (expected 'Raw Results' or a sheet with Suite/Flow and Status)."

        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            return [], "Empty sheet."

        headers = [str(h or "").strip() for h in header_row]
        i_suite = _col_index(headers, "Suite")
        i_flow = _col_index(headers, "Flow Name", "Flow")
        i_dname = _col_index(headers, "Device Name", "Device")
        i_did = _col_index(headers, "Device ID", "Device Id", "Udid", "UDID")
        i_status = _col_index(headers, "Status")
        i_exit = _col_index(headers, "Exit Code", "Exit code")

        if i_status is None:
            return [], "No 'Status' column in execution data."

        out: list[dict[str, str]] = []
        for row in rows_iter:
            if not row:
                continue
            if all(v is None or str(v).strip() == "" for v in row):
                continue

            def _cell(i: int | None) -> str:
                if i is None or i >= len(row):
                    return ""
                v = row[i]
                return "" if v is None else str(v).strip()

            suite = _cell(i_suite)
            flow = _cell(i_flow)
            device = _cell(i_dname)
            if not device:
                device = _cell(i_did)
            st = _cell(i_status).upper() or "UNKNOWN"
            ex = _cell(i_exit)
            if ex == "":
                ex = "0"

            out.append(
                {
                    "suite": suite,
                    "flow": flow,
                    "device": device,
                    "status": st,
                    "exit_code": ex,
                }
            )
        return out, None
    finally:
        wb.close()


def _status_html_class(status: str) -> str:
    u = (status or "").upper()
    if u == "PASS":
        return "st-pass"
    if u in ("FAIL", "PARSE_ERROR", "ERROR"):
        return "st-fail"
    if u == "FLAKY":
        return "st-flaky"
    return "st-other"


def build_email_html(
    rows: list[dict[str, str]], generated_on: str, error_note: str | None
) -> str:
    if error_note and not rows:
        table_body = (
            f'<p class="warn">{html.escape(error_note)}</p>'
            "<p><em>No execution rows to display.</em></p>"
        )
    else:
        trs = []
        for r in rows:
            cls = _status_html_class(r["status"])
            trs.append(
                "<tr>"
                f'<td class="c-suite">{html.escape(r["suite"])}</td>'
                f'<td class="c-flow">{html.escape(r["flow"])}</td>'
                f'<td class="c-dev">{html.escape(r["device"])}</td>'
                f'<td class="{cls}"><strong>{html.escape(r["status"])}</strong></td>'
                f'<td class="c-ex">{html.escape(r["exit_code"])}</td>'
                "</tr>"
            )
        if not trs:
            table_body = (
                f'<p class="warn">{html.escape(error_note or "No data rows in report.")}</p>'
            )
        else:
            if error_note:
                table_body = f'<p class="warn">{html.escape(error_note)}</p><table class="ex">{_thead()}{"".join(trs)}</table>'
            else:
                table_body = f'<table class="ex">{_thead()}{"".join(trs)}</table>'

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Calibri, "Segoe UI", Arial, sans-serif; font-size: 14px; color: #1a1a1a; }}
  h1 {{ color: #1f4e79; font-size: 20px; margin-bottom: 8px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 16px; }}
  .warn {{ color: #a94442; background: #fbe8e6; padding: 8px; border-radius: 4px; }}
  table.ex {{ border-collapse: collapse; width: 100%; max-width: 1000px; border: 1px solid #ccc; }}
  table.ex th, table.ex td {{ border: 1px solid #d0d0d0; padding: 8px 10px; text-align: left; vertical-align: top; word-break: break-word; }}
  table.ex th {{ background: #2e5c8a; color: #fff; font-weight: 600; }}
  .st-pass {{ color: #1b5e20; background: #e8f5e9; font-weight: bold; }}
  .st-fail {{ color: #b71c1c; background: #ffebee; font-weight: bold; }}
  .st-flaky {{ color: #e65100; background: #fff3e0; font-weight: bold; }}
  .st-other {{ color: #333; background: #f5f5f5; font-weight: bold; }}
</style>
</head>
<body>
  <h1>Kodak Smile Execution Summary</h1>
  <p class="sub">Generated on: {html.escape(generated_on)}</p>
  {table_body}
  <p class="sub" style="margin-top:20px;">This message was sent by Jenkins automation. The detailed workbook is attached.</p>
</body>
</html>"""


def _thead() -> str:
    return (
        "<tr>"
        "<th>Suite</th><th>Flow</th><th>Device</th><th>Status</th><th>Exit Code</th>"
        "</tr>"
    )


def build_email_plain(
    rows: list[dict[str, str]], generated_on: str, error_note: str | None
) -> str:
    lines = [
        "Kodak Smile Execution Summary",
        "",
        f"Generated on: {generated_on}",
        "",
    ]
    if error_note:
        lines.append(error_note)
        lines.append("")
    if not rows:
        lines.append("No execution rows in the report table.")
    else:
        colw = (14, 28, 20, 10, 10)
        lines.append("Suite | Flow | Device | Status | Exit Code")
        lines.append("-" * 72)
        for r in rows:
            line = " | ".join(
                [
                    (r["suite"] or "")[: colw[0]],
                    (r["flow"] or "")[: colw[1]],
                    (r["device"] or "")[: colw[2]],
                    (r["status"] or "")[: colw[3]],
                    (r["exit_code"] or "")[: colw[4]],
                ]
            )
            lines.append(line)
    lines.extend(["", "See attached final_execution_report.xlsx for full details."])
    return "\n".join(lines)


def getenv_any(*names: str, default: str = "") -> str:
    for name in names:
        v = os.getenv(name, "").strip()
        if v:
            return v
    return default


def _orch_email_strict() -> bool:
    return (os.environ.get("ORCH_EMAIL_STRICT", "").strip().lower() in ("1", "true", "yes", "on"))


def _smtp_config_ready() -> bool:
    """
    True when user/pass/receiver and server (or implied Gmail) are all present to attempt SMTP.
    """
    smtp_user = getenv_any("SMTP_USER", "SENDER_EMAIL", "GMAIL_USER")
    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
    if not smtp_server and smtp_user and "@" in smtp_user and smtp_user.lower().rstrip().endswith(
        ("@gmail.com", "@googlemail.com")
    ):
        smtp_server = "smtp.gmail.com"
    smtp_pass = getenv_any("SMTP_PASS", "SMTP_PASSWORD", "SENDER_PASSWORD", "GMAIL_APP_PASSWORD")
    receiver = getenv_any("RECEIVER_EMAIL", "MAIL_TO", "EMAIL_RECIPIENTS", "RECIPIENT", "ORCH_MAIL_TO")
    return bool(smtp_server and smtp_user and smtp_pass and receiver)


def send_execution_report_email(
    excel_path: Path,
    *,
    root: Path | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> bool:
    """
    Returns True if mail was sent, False if skipped or failed (logged).
    HTML body is built from final_execution_report.xlsx unless ``body`` is set (overrides).
    """
    excel_path = excel_path.resolve()
    if not excel_path.is_file():
        logger.error("Excel attachment missing: %s", excel_path)
        return False

    smtp_user = getenv_any("SMTP_USER", "SENDER_EMAIL", "GMAIL_USER")
    smtp_server = getenv_any("SMTP_SERVER", "SMTP_HOST")
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
        "ORCH_MAIL_SUBJECT",
        default="Jenkins Execution Report",
    )

    gen_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if body is not None:
        text_body = body
        html_body = f"<html><body><pre>{html.escape(body)}</pre></body></html>"
    else:
        table_rows, table_err = read_execution_table_rows(excel_path)
        text_body = build_email_plain(table_rows, gen_ts, table_err)
        html_body = build_email_html(table_rows, gen_ts, table_err)

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
    msg.add_alternative(html_body, subtype="html")

    msg.add_attachment(
        excel_path.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=excel_path.name,
    )

    logs_zip = resolve_execution_logs_zip(excel_path, root)
    if logs_zip is not None:
        msg.add_attachment(
            logs_zip.read_bytes(),
            maintype="application",
            subtype="zip",
            filename=logs_zip.name,
        )
        logger.info("Attached: %s", logs_zip)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_server, port, timeout=60) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Email sent to %s (HTML + attachments)", receiver)
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
    if not _smtp_config_ready():
        if _orch_email_strict():
            logger.error(
                "ORCH_EMAIL_STRICT=1: SMTP is not fully configured. "
                "Jenkins: in the Send Final Email stage set SMTP_USER, SMTP_PASS, RECEIVER_EMAIL (e.g. in the batch step), "
                "or export them on the agent before: python mailout/send_email.py"
            )
            return 1
        logger.warning(
            "SMTP not configured (set SMTP_USER + SMTP_PASS + RECEIVER_EMAIL, and SMTP_SERVER or @gmail.com); "
            "exiting 0. Set ORCH_EMAIL_STRICT=1 to fail this step if mail is required."
        )
        return 0
    return 0 if send_execution_report_email(excel, root=root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
