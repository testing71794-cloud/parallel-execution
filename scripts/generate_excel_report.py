import csv
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("Usage: generate_excel_report.py <source_dir> <output_dir>")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    if source_dir.exists():
        for status_file in sorted(source_dir.rglob("*.pass")):
            rows.append([status_file.stem, "PASS", str(status_file)])
        for status_file in sorted(source_dir.rglob("*.fail")):
            rows.append([status_file.stem, "FAIL", str(status_file)])

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
        f.write("</table></body></html>")

if __name__ == "__main__":
    main()
