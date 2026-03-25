import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

project_root = os.getcwd()
input_dir_name = sys.argv[1] if len(sys.argv) > 1 else "reports"
output_file_name = sys.argv[2] if len(sys.argv) > 2 else "summary.xlsx"
suite_name = sys.argv[3] if len(sys.argv) > 3 else "suite"

reports_dir = os.path.join(project_root, input_dir_name)
output_file = os.path.join(reports_dir, output_file_name)
os.makedirs(reports_dir, exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "Execution Summary"
headers = ["Suite", "Build Number", "Timestamp", "Device ID", "Flow Name", "Status", "Duration (s)", "Failure Reason"]
ws.append(headers)

header_fill = PatternFill("solid", fgColor="1F4E78")
header_font = Font(color="FFFFFF", bold=True)
for idx in range(1, len(headers) + 1):
    cell = ws.cell(row=1, column=idx)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center")

build_number = os.environ.get("BUILD_NUMBER", "")
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for device_id in sorted(os.listdir(reports_dir)) if os.path.isdir(reports_dir) else []:
    device_path = os.path.join(reports_dir, device_id)
    report_file = os.path.join(device_path, "report.xml")
    if not os.path.isdir(device_path) or not os.path.exists(report_file):
        continue
    try:
        tree = ET.parse(report_file)
        root = tree.getroot()
        testcases = root.findall(".//testcase")
        if not testcases:
            ws.append([suite_name, build_number, timestamp, device_id, "NO_TESTCASE_FOUND", "Failed", "", "No testcase entries in report.xml"])
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
            ws.append([suite_name, build_number, timestamp, device_id, flow_name, status, duration, failure_reason])
    except Exception as exc:
        ws.append([suite_name, build_number, timestamp, device_id, "REPORT_PARSE_ERROR", "Failed", "", str(exc)])

for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=6, max_col=6):
    for cell in row:
        if cell.value == "Passed":
            cell.font = Font(color="008000", bold=True)
        elif cell.value == "Failed":
            cell.font = Font(color="FF0000", bold=True)

for col in range(1, ws.max_column + 1):
    letter = get_column_letter(col)
    max_length = max((len(str(cell.value)) if cell.value is not None else 0) for cell in ws[letter])
    ws.column_dimensions[letter].width = min(max_length + 2, 45)

wb.save(output_file)
print(f"Excel report generated: {output_file}")
