import os
import xml.etree.ElementTree as ET
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

PROJECT_ROOT = os.getcwd()
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
OUTPUT_FILE = os.path.join(REPORTS_DIR, "maestro_summary.xlsx")

#  FIX: Ensure reports folder exists
os.makedirs(REPORTS_DIR, exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "Execution Summary"

headers = [
    "Build Number",
    "Timestamp",
    "Device ID",
    "Flow Name",
    "Status",
    "Duration (s)",
    "Failure Reason"
]
ws.append(headers)

header_fill = PatternFill("solid", fgColor="1F4E78")
header_font = Font(color="FFFFFF", bold=True)

for col_idx, header in enumerate(headers, start=1):
    cell = ws.cell(row=1, column=col_idx)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center")

build_number = os.environ.get("BUILD_NUMBER", "")
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Process device-wise reports
if os.path.isdir(REPORTS_DIR):
    for device_id in os.listdir(REPORTS_DIR):
        device_path = os.path.join(REPORTS_DIR, device_id)
        report_file = os.path.join(device_path, "report.xml")

        if not os.path.isdir(device_path):
            continue
        if not os.path.exists(report_file):
            continue

        try:
            tree = ET.parse(report_file)
            root = tree.getroot()

            testcases = root.findall(".//testcase")
            for tc in testcases:
                flow_name = tc.attrib.get("name", "")
                duration = tc.attrib.get("time", "")
                failure = tc.find("failure")

                if failure is None:
                    status = "Passed"
                    failure_reason = ""
                else:
                    status = "Failed"
                    failure_reason = failure.attrib.get("message", "") or (failure.text or "").strip()

                ws.append([
                    build_number,
                    timestamp,
                    device_id,
                    flow_name,
                    status,
                    duration,
                    failure_reason
                ])
        except Exception as e:
            ws.append([
                build_number,
                timestamp,
                device_id,
                "REPORT_PARSE_ERROR",
                "Failed",
                "",
                str(e)
            ])

# Color formatting
for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=5, max_col=5):
    for cell in row:
        if cell.value == "Passed":
            cell.font = Font(color="008000", bold=True)
        elif cell.value == "Failed":
            cell.font = Font(color="FF0000", bold=True)

# Auto column width
for col in range(1, ws.max_column + 1):
    max_length = 0
    col_letter = get_column_letter(col)
    for cell in ws[col_letter]:
        value = "" if cell.value is None else str(cell.value)
        max_length = max(max_length, len(value))
    ws.column_dimensions[col_letter].width = min(max_length + 2, 45)

wb.save(OUTPUT_FILE)

print(fExcel report generated: {OUTPUT_FILE}")