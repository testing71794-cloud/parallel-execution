#!/usr/bin/env python3
"""
Enhanced Excel report generator for Jenkins/Maestro execution results.

Usage:
    python scripts/generate_excel_report.py <status_dir> <output_dir> <suite_name>

Example:
    python scripts/generate_excel_report.py status reports\nonprinting_summary nonprinting

What it generates in <output_dir>:
    - summary.xlsx   -> Excel workbook with device-wise and flow-wise summaries
    - all_results.csv
    - failed_results.csv
    - passed_results.csv
"""

from __future__ import annotations

import csv
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


PASS_FILL = PatternFill(fill_type="solid", fgColor="C6EFCE")
FAIL_FILL = PatternFill(fill_type="solid", fgColor="FFC7CE")
HEADER_FILL = PatternFill(fill_type="solid", fgColor="D9EAF7")
TITLE_FILL = PatternFill(fill_type="solid", fgColor="B4C7E7")


def parse_status_file(file_path: Path) -> dict:
    data = {
        "suite": "",
        "flow": "",
        "device": "",
        "status": "",
        "log": "",
        "exit_code": "",
        "file_name": file_path.name,
    }

    try:
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip().lower()] = value.strip()
    except Exception as exc:
        data["status"] = "PARSE_ERROR"
        data["log"] = f"Could not parse file: {exc}"

    if not data["flow"]:
        stem = file_path.stem
        parts = stem.split("__")
        if len(parts) >= 3:
            data["suite"] = data["suite"] or parts[0]
            data["flow"] = data["flow"] or parts[1]
            data["device"] = data["device"] or parts[2]

    data["status"] = (data.get("status") or "UNKNOWN").upper()
    return data


def load_results(status_dir: Path, suite_name: str) -> list[dict]:
    if not status_dir.exists():
        return []

    results = []
    for file_path in sorted(status_dir.glob("*.txt")):
        row = parse_status_file(file_path)
        row_suite = (row.get("suite") or "").strip().lower()
        if suite_name and row_suite and row_suite != suite_name.lower():
            continue
        results.append(row)

    return results


def autosize(ws):
    for col_cells in ws.columns:
        max_len = 0
        col_index = col_cells[0].column
        for cell in col_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        ws.column_dimensions[get_column_letter(col_index)].width = min(max(max_len + 2, 12), 60)


def style_header(row):
    for cell in row:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")


def write_table(ws, start_row: int, title: str, headers: list[str], rows: list[list]):
    title_cell = ws.cell(row=start_row, column=1, value=title)
    title_cell.font = Font(bold=True, size=12)
    title_cell.fill = TITLE_FILL

    header_row_idx = start_row + 1
    for idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row_idx, column=idx, value=header)

    style_header(ws[header_row_idx])

    current_row = header_row_idx + 1
    for row_values in rows:
        for idx, value in enumerate(row_values, start=1):
            ws.cell(row=current_row, column=idx, value=value)
        current_row += 1

    return current_row + 1


def build_workbook(results: list[dict], output_file: Path, suite_name: str):
    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary"

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] != "PASS")

    devices = sorted({r.get("device", "") for r in results if r.get("device", "")})
    flows = sorted({r.get("flow", "") for r in results if r.get("flow", "")})

    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary_rows = [
        ["Suite", suite_name],
        ["Generated On", generated_on],
        ["Total Results", total],
        ["Passed", passed],
        ["Failed", failed],
        ["Devices Covered", len(devices)],
        ["Flows Covered", len(flows)],
    ]

    for r_idx, row in enumerate(summary_rows, start=1):
        ws_summary.cell(row=r_idx, column=1, value=row[0]).font = Font(bold=True)
        ws_summary.cell(row=r_idx, column=2, value=row[1])

    # Flow-wise summary
    flow_counter = defaultdict(lambda: Counter())
    for row in results:
        flow_counter[row["flow"]][row["status"]] += 1

    flow_rows = []
    for flow in sorted(flow_counter):
        flow_rows.append([
            flow,
            flow_counter[flow]["PASS"],
            sum(v for k, v in flow_counter[flow].items() if k != "PASS"),
            sum(flow_counter[flow].values()),
        ])

    next_row = write_table(
        ws_summary,
        10,
        "Flow-wise Summary",
        ["Flow", "Pass", "Fail", "Total"],
        flow_rows,
    )

    # Device-wise summary
    device_counter = defaultdict(lambda: Counter())
    for row in results:
        device_counter[row["device"]][row["status"]] += 1

    device_rows = []
    for device in sorted(device_counter):
        device_rows.append([
            device,
            device_counter[device]["PASS"],
            sum(v for k, v in device_counter[device].items() if k != "PASS"),
            sum(device_counter[device].values()),
        ])

    write_table(
        ws_summary,
        next_row,
        "Device-wise Summary",
        ["Device", "Pass", "Fail", "Total"],
        device_rows,
    )

    autosize(ws_summary)

    # All Results
    ws_all = wb.create_sheet("All Results")
    all_headers = ["Suite", "Flow", "Device", "Status", "Exit Code", "Log", "Source File"]
    ws_all.append(all_headers)
    style_header(ws_all[1])

    for row in results:
        ws_all.append([
            row.get("suite", ""),
            row.get("flow", ""),
            row.get("device", ""),
            row.get("status", ""),
            row.get("exit_code", ""),
            row.get("log", ""),
            row.get("file_name", ""),
        ])

    for row in ws_all.iter_rows(min_row=2):
        status_cell = row[3]
        if status_cell.value == "PASS":
            status_cell.fill = PASS_FILL
        else:
            status_cell.fill = FAIL_FILL
    autosize(ws_all)

    # Failed Results
    ws_failed = wb.create_sheet("Failed Results")
    ws_failed.append(all_headers)
    style_header(ws_failed[1])
    for row in results:
        if row.get("status") != "PASS":
            ws_failed.append([
                row.get("suite", ""),
                row.get("flow", ""),
                row.get("device", ""),
                row.get("status", ""),
                row.get("exit_code", ""),
                row.get("log", ""),
                row.get("file_name", ""),
            ])
    for row in ws_failed.iter_rows(min_row=2):
        row[3].fill = FAIL_FILL
    autosize(ws_failed)

    # Passed Results
    ws_passed = wb.create_sheet("Passed Results")
    ws_passed.append(all_headers)
    style_header(ws_passed[1])
    for row in results:
        if row.get("status") == "PASS":
            ws_passed.append([
                row.get("suite", ""),
                row.get("flow", ""),
                row.get("device", ""),
                row.get("status", ""),
                row.get("exit_code", ""),
                row.get("log", ""),
                row.get("file_name", ""),
            ])
    for row in ws_passed.iter_rows(min_row=2):
        row[3].fill = PASS_FILL
    autosize(ws_passed)

    # Per-device detail sheet
    ws_device = wb.create_sheet("Per Device Detail")
    device_headers = ["Device", "Flow", "Status", "Exit Code", "Log"]
    ws_device.append(device_headers)
    style_header(ws_device[1])

    for row in sorted(results, key=lambda x: (x.get("device", ""), x.get("flow", ""))):
        ws_device.append([
            row.get("device", ""),
            row.get("flow", ""),
            row.get("status", ""),
            row.get("exit_code", ""),
            row.get("log", ""),
        ])
    for row in ws_device.iter_rows(min_row=2):
        if row[2].value == "PASS":
            row[2].fill = PASS_FILL
        else:
            row[2].fill = FAIL_FILL
    autosize(ws_device)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_file)


def write_csv(path: Path, rows: list[dict], only_status: str | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["suite", "flow", "device", "status", "exit_code", "log", "file_name"]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            if only_status == "PASS" and row.get("status") != "PASS":
                continue
            if only_status == "FAIL" and row.get("status") == "PASS":
                continue
            writer.writerow({h: row.get(h, "") for h in headers})


def main():
    if len(sys.argv) != 4:
        print("Usage: python scripts/generate_excel_report.py <status_dir> <output_dir> <suite_name>")
        sys.exit(1)

    status_dir = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    suite_name = sys.argv[3].strip().lower()

    output_dir.mkdir(parents=True, exist_ok=True)

    results = load_results(status_dir, suite_name)

    output_file = output_dir / "summary.xlsx"
    build_workbook(results, output_file, suite_name)

    write_csv(output_dir / "all_results.csv", results)
    write_csv(output_dir / "failed_results.csv", results, only_status="FAIL")
    write_csv(output_dir / "passed_results.csv", results, only_status="PASS")

    print(f"Report generated successfully: {output_file}")
    print(f"Total results: {len(results)}")


if __name__ == "__main__":
    main()
