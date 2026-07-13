"""Reporting package — HTML / PDF / Markdown / JSON / QA sign-off.

Writes only under ``ai-agent/reports`` and ``artifacts`` — does not replace existing Excel pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from models import RegressionSummary, ReleaseVerdict, TestStatus

logger = logging.getLogger("ai-agent.reporting")


class ReportGenerator:
    def __init__(self, report_root: Path) -> None:
        self.root = Path(report_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_all(self, summary: RegressionSummary) -> dict[str, Path]:
        paths = {
            "json": self.write_json(summary),
            "markdown": self.write_markdown(summary),
            "html": self.write_html(summary),
            "pdf": self.write_pdf(summary),
            "signoff": self.write_signoff(summary),
            "failed_tests": self.write_failed_tests(summary),
        }
        logger.info("reports written under %s", self.root)
        return paths

    def write_failed_tests(self, summary: RegressionSummary) -> Path:
        """Failed-tests-only table (Suite/Flow/Device/Status/Reason/AI/Screenshot/Video)."""
        from reporting.failed_tests_report import (
            merge_failed_rows,
            render_failed_tests_html,
            load_failed_summary,
            jenkins_artifact_url,
        )

        # Prefer build-summary artifacts; also map module-level agent failures.
        repo = self.root.parent.parent if self.root.name == "reports" else Path.cwd()
        # ai-agent/reports → repo is parents[1]
        repo = Path(summary.artifact_root).resolve().parent if summary.artifact_root else self.root
        # artifact_root is <repo>/artifacts → parent is repo
        if (self.root.parent / "ATP TestCase Flows").is_dir():
            repo = self.root.parent
        elif (self.root.parent.parent / "ATP TestCase Flows").is_dir():
            repo = self.root.parent.parent

        excel_like: list[dict] = []
        for m in summary.modules:
            if m.status.value in ("FAIL", "RETRIED_FAIL"):
                excel_like.append(
                    {
                        "suite": f"atp_{m.module.lower()}",
                        "test_name": m.module,
                        "flow": m.module,
                        "device": m.device_model or m.device_serial,
                        "device_id": m.device_serial,
                        "status": "FAIL",
                        "failure_reason": "MAESTRO_FAILED",
                        "ai_analysis": (
                            m.failure.root_cause if m.failure else "—"
                        ),
                        "screenshot_artifact": Path(m.screenshot_paths[0]).name
                        if m.screenshot_paths
                        else "",
                        "video_artifact": Path(m.video_paths[0]).name if m.video_paths else "",
                    }
                )
        rows = merge_failed_rows(
            summary_rows=load_failed_summary(repo),
            excel_fail_rows=excel_like,
        )
        zip_path = repo / "build-summary" / "failed_tests_artifacts.zip"
        artifact_url = None
        if zip_path.is_file():
            artifact_url = jenkins_artifact_url("build-summary/failed_tests_artifacts.zip") or zip_path.as_uri()
        path = self.root / "failed_tests.html"
        path.write_text(
            render_failed_tests_html(rows, artifact_url=artifact_url),
            encoding="utf-8",
        )
        return path

    def write_json(self, summary: RegressionSummary) -> Path:
        path = self.root / "report.json"
        path.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_markdown(self, summary: RegressionSummary) -> Path:
        path = self.root / "summary.md"
        lines = [
            f"# Kodak Smile Android Regression",
            "",
            f"- **Build:** {summary.build}",
            f"- **Date:** {summary.date_iso}",
            f"- **App:** `{summary.app_package}`",
            f"- **Total Tests:** {summary.total_tests}",
            f"- **Passed:** {summary.passed}",
            f"- **Failed:** {summary.failed}",
            f"- **Skipped:** {summary.skipped}",
            f"- **Duration (s):** {summary.duration_sec:.1f}",
            f"- **Recommendation:** **{summary.recommendation.value}**",
            "",
            "## Devices",
            "",
        ]
        for d in summary.devices:
            lines.append(
                f"- `{d.serial}` — {d.model or 'unknown'} (Android {d.android_version or '?'})"
            )
        lines += ["", "## Modules", ""]
        for m in summary.modules:
            lines.append(
                f"- **{m.module}**: {m.status.value} "
                f"(pass={m.passed} fail={m.failed} skip={m.skipped} "
                f"duration={m.duration_sec}s)"
            )
            if m.failure:
                lines.append(
                    f"  - Failure: `{m.failure.category.value}` "
                    f"({m.failure.confidence:.2f}) — {m.failure.root_cause}"
                )
        lines += ["", "## Top Issues", ""]
        for issue in summary.top_issues or ["(none)"]:
            lines.append(f"- {issue}")
        lines += ["", "## Critical Issues", ""]
        for issue in summary.critical_issues or ["(none)"]:
            lines.append(f"- {issue}")
        lines += ["", "## Crash Summary", ""]
        for c in summary.crash_summary or ["(none)"]:
            lines.append(f"- {c}")
        lines += ["", "## Coverage", "", summary.coverage_notes or "(auto-discovered ATP modules)", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def write_html(self, summary: RegressionSummary) -> Path:
        path = self.root / "report.html"
        verdict_color = "#0a7a32" if summary.recommendation == ReleaseVerdict.READY_FOR_RELEASE else "#b00020"
        rows = []
        for m in summary.modules:
            fail_cell = ""
            if m.failure:
                fail_cell = f"{m.failure.category.value} ({m.failure.confidence:.2f})"
            rows.append(
                "<tr>"
                f"<td>{_esc(m.module)}</td>"
                f"<td>{_esc(m.status.value)}</td>"
                f"<td>{m.passed}</td><td>{m.failed}</td><td>{m.skipped}</td>"
                f"<td>{m.duration_sec}</td>"
                f"<td>{_esc(m.device_model or m.device_serial)}</td>"
                f"<td>{_esc(fail_cell)}</td>"
                "</tr>"
            )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Kodak Smile AI Agent Report</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1a1a1a; }}
h1 {{ margin-bottom: 4px; }}
.meta {{ color: #555; margin-bottom: 20px; }}
.verdict {{ display:inline-block; padding:8px 14px; color:#fff; background:{verdict_color}; border-radius:6px; font-weight:600; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 14px; }}
th {{ background: #f4f4f4; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }}
.card {{ background:#fafafa; border:1px solid #e5e5e5; border-radius:8px; padding:12px 16px; min-width:120px; }}
.card b {{ display:block; font-size:22px; }}
</style>
</head>
<body>
<h1>Kodak Smile Android Regression</h1>
<div class="meta">Build { _esc(summary.build) } · { _esc(summary.date_iso) } · { _esc(summary.app_package) }</div>
<div class="verdict">{ _esc(summary.recommendation.value) }</div>
<div class="cards">
  <div class="card"><span>Total</span><b>{summary.total_tests}</b></div>
  <div class="card"><span>Passed</span><b>{summary.passed}</b></div>
  <div class="card"><span>Failed</span><b>{summary.failed}</b></div>
  <div class="card"><span>Skipped</span><b>{summary.skipped}</b></div>
  <div class="card"><span>Duration (s)</span><b>{summary.duration_sec:.0f}</b></div>
</div>
<h2>Modules</h2>
<table>
<thead><tr><th>Module</th><th>Status</th><th>Pass</th><th>Fail</th><th>Skip</th><th>Time</th><th>Device</th><th>Failure</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<h2>Top Issues</h2>
<ul>{''.join(f'<li>{_esc(i)}</li>' for i in (summary.top_issues or ['(none)']))}</ul>
<h2>Critical Issues</h2>
<ul>{''.join(f'<li>{_esc(i)}</li>' for i in (summary.critical_issues or ['(none)']))}</ul>
<h2>Crash Summary</h2>
<ul>{''.join(f'<li>{_esc(i)}</li>' for i in (summary.crash_summary or ['(none)']))}</ul>
<p class="meta">Artifacts: {_esc(summary.artifact_root)}</p>
</body>
</html>
"""
        path.write_text(html, encoding="utf-8")
        return path

    def write_pdf(self, summary: RegressionSummary) -> Path:
        """Generate PDF via reportlab when installed; otherwise a minimal built-in PDF."""
        path = self.root / "report.pdf"
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(str(path), pagesize=letter)
            width, height = letter
            y = height - 50
            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, y, "Kodak Smile Android Regression")
            y -= 24
            c.setFont("Helvetica", 10)
            for line in [
                f"Build: {summary.build}",
                f"Date: {summary.date_iso}",
                f"Total: {summary.total_tests}  Passed: {summary.passed}  Failed: {summary.failed}  Skipped: {summary.skipped}",
                f"Recommendation: {summary.recommendation.value}",
                "",
                "Modules:",
            ]:
                c.drawString(40, y, line[:110])
                y -= 14
                if y < 60:
                    c.showPage()
                    y = height - 50
            for m in summary.modules:
                line = f"- {m.module}: {m.status.value} ({m.duration_sec}s)"
                c.drawString(50, y, line[:100])
                y -= 14
                if y < 60:
                    c.showPage()
                    y = height - 50
            c.save()
            return path
        except Exception as exc:  # noqa: BLE001
            logger.warning("reportlab unavailable (%s) — using built-in PDF writer", exc)
            lines = [
                "Kodak Smile Android Regression",
                f"Build: {summary.build}",
                f"Date: {summary.date_iso}",
                f"Total: {summary.total_tests} Passed: {summary.passed} Failed: {summary.failed} Skipped: {summary.skipped}",
                f"Recommendation: {summary.recommendation.value}",
                "",
                "Modules:",
            ]
            for m in summary.modules:
                lines.append(f"- {m.module}: {m.status.value} ({m.duration_sec}s)")
            path.write_bytes(_minimal_pdf("\n".join(lines)))
            twin = self.root / "report.pdf.txt"
            twin.write_text("\n".join(lines), encoding="utf-8")
            return path

    def write_signoff(self, summary: RegressionSummary) -> Path:
        path = self.root / "QA_SIGNOFF.md"
        modules = ", ".join(m.module for m in summary.modules) or "(none)"
        text = f"""Kodak Smile Android Regression

Build: {summary.build}
Date: {summary.date_iso}

Total Tests: {summary.total_tests}
Passed: {summary.passed}
Failed: {summary.failed}

Automation Coverage
{summary.coverage_notes or 'Auto-discovered ATP TestCase Flows modules'}

Modules Tested
{modules}

Top Failures
{chr(10).join('- ' + i for i in (summary.top_issues or ['(none)']))}

Critical Issues
{chr(10).join('- ' + i for i in (summary.critical_issues or ['(none)']))}

Recommendation

{summary.recommendation.value}
"""
        path.write_text(text, encoding="utf-8")
        return path


def _minimal_pdf(text: str) -> bytes:
    """Tiny single-page PDF without third-party deps (Courier text)."""
    # Escape PDF string specials
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_lines = ["BT", "/F1 10 Tf", "50 750 Td", "12 TL"]
    first = True
    for raw in safe.splitlines()[:60]:
        if first:
            content_lines.append(f"({raw[:100]}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({raw[:100]}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>endobj\n")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def decide_verdict(summary: RegressionSummary) -> ReleaseVerdict:
    """Conservative gate: any failed module or crash → NOT READY."""
    if summary.failed > 0:
        return ReleaseVerdict.NOT_READY
    if summary.critical_issues:
        return ReleaseVerdict.NOT_READY
    if summary.total_tests <= 0:
        return ReleaseVerdict.NOT_READY
    return ReleaseVerdict.READY_FOR_RELEASE


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
