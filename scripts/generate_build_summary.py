import json
import sys
from pathlib import Path
from html import escape

SEPARATOR = "__"


def parse_status_files(status_dir: Path):
    rows = []
    if not status_dir.exists():
        return rows
    for path in sorted(status_dir.glob("*.*")):
        parts = path.stem.split(SEPARATOR)
        if len(parts) < 3:
            continue
        suite = parts[0]
        flow = parts[1]
        device = SEPARATOR.join(parts[2:])
        status = "PASS" if path.suffix.lower() == ".pass" else "FAIL"
        rows.append({"suite": suite, "flow": flow, "device": device, "status": status, "path": str(path)})
    return rows


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_build_summary.py <collected-artifacts-dir> <output-dir>")
        sys.exit(1)

    collected = Path(sys.argv[1])
    output = Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)

    rows = parse_status_files(collected / "status")
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "PASS")
    failed = sum(1 for r in rows if r["status"] == "FAIL")

    payload = {"total": total, "passed": passed, "failed": failed, "rows": rows}
    (output / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    html_rows = []
    for row in rows:
        html_rows.append(
            f"<tr><td>{escape(row['suite'])}</td><td>{escape(row['flow'])}</td><td>{escape(row['device'])}</td><td>{escape(row['status'])}</td><td>{escape(row['path'])}</td></tr>"
        )

    html = f"""<html><head><meta charset=\"utf-8\"><title>Kodak Smile Pipeline Summary</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:8px;text-align:left}}th{{background:#f5f5f5}}</style>
</head><body>
<h2>Kodak Smile Pipeline Summary</h2>
<p>Total: <strong>{total}</strong></p>
<p>Passed: <strong>{passed}</strong></p>
<p>Failed: <strong>{failed}</strong></p>
<table><thead><tr><th>Suite</th><th>Flow</th><th>Device</th><th>Status</th><th>Path</th></tr></thead><tbody>
{''.join(html_rows) if html_rows else '<tr><td colspan="5">No status files found.</td></tr>'}
</tbody></table></body></html>"""
    (output / "summary.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
