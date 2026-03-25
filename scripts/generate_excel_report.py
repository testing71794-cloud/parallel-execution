import csv
import sys
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font

SEPARATOR = "__"


def parse_status_name(path: Path):
    parts = path.stem.split(SEPARATOR)
    if len(parts) < 3:
        return None
    suite = parts[0]
    flow = parts[1]
    device = SEPARATOR.join(parts[2:])
    status = "PASS" if path.suffix.lower() == ".pass" else "FAIL"
    return {
        "suite": suite,
        "flow": flow,
        "device": device,
        "status": status,
        "path": str(path),
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: generate_excel_report.py <status_dir> <output_dir> <suite_prefix>")
        sys.exit(1)

    status_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    suite_prefix = sys.argv[3].strip().lower()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    if status_dir.exists():
        for status_file in sorted(status_dir.glob(f"{suite_prefix}{SEPARATOR}*.*")):
            row = parse_status_name(status_file)
            if row:
                rows.append(row)

    csv_path = output_dir / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["suite", "flow", "device", "status", "path"])
        for row in rows:
            writer.writerow([row["suite"], row["flow"], row["device"], row["status"], row["path"]])

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    headers = ["suite", "flow", "device", "status", "path"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row["suite"], row["flow"], row["device"], row["status"], row["path"]])
    if not rows:
        ws.append([suite_prefix, "No status files found", "", "", ""])
    for col in ["A", "B", "C", "D", "E"]:
        ws.column_dimensions[col].width = 28
    wb.save(output_dir / "summary.xlsx")

    html_path = output_dir / "summary.html"
    with html_path.open("w", encoding="utf-8") as f:
        f.write("<html><body><h3>Suite Summary</h3><table border='1'><tr><th>Suite</th><th>Flow</th><th>Device</th><th>Status</th><th>Path</th></tr>")
        if rows:
            for row in rows:
                f.write(f"<tr><td>{row['suite']}</td><td>{row['flow']}</td><td>{row['device']}</td><td>{row['status']}</td><td>{row['path']}</td></tr>")
        else:
            f.write("<tr><td colspan='5'>No status files found.</td></tr>")
        f.write("</table></body></html>")


if __name__ == "__main__":
    main()
