import csv
import sys
from pathlib import Path

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
        for status_file in sorted(status_dir.glob(f"{suite_prefix}_*.*")):
            name = status_file.stem
            status = "PASS" if status_file.suffix.lower() == ".pass" else "FAIL"
            rows.append([name, status, str(status_file)])

    csv_path = output_dir / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "status", "path"])
        writer.writerows(rows)

    html_path = output_dir / "summary.html"
    with html_path.open("w", encoding="utf-8") as f:
        f.write("<html><body><h3>Suite Summary</h3><table border='1'><tr><th>Name</th><th>Status</th><th>Path</th></tr>")
        for row in rows:
            f.write(f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td></tr>")
        if not rows:
            f.write("<tr><td colspan='3'>No status files found.</td></tr>")
        f.write("</table></body></html>")

if __name__ == "__main__":
    main()
