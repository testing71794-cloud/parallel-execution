"""Failed-tests-only HTML report — matches Jenkins email Failed Tests table.

Columns: Suite | Flow | Device | Status | Failure Reason | AI Analysis | Screenshot | Video
Footer: Failed Test Artifacts zip link (Jenkins BUILD_URL when available).
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any


FAILURE_STATUSES = frozenset({"FAIL", "FLAKY", "PARSE_ERROR", "ERROR"})


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default


def jenkins_artifact_url(relative_path: str) -> str | None:
    base = _env("BUILD_URL", "JENKINS_BUILD_URL").rstrip("/")
    if not base:
        return None
    rel = relative_path.lstrip("/").replace("\\", "/")
    return f"{base}/artifact/{rel}"


def load_failed_summary(repo: Path) -> list[dict[str, Any]]:
    path = repo.resolve() / "build-summary" / "failed_tests_summary.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("failures") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def rows_from_excel_failures(excel_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in excel_rows:
        st = (r.get("status") or "").upper()
        if st not in FAILURE_STATUSES:
            continue
        out.append(
            {
                "suite": r.get("suite") or "",
                "test_name": r.get("flow") or r.get("test_name") or "",
                "flow": r.get("flow") or "",
                "device": r.get("device") or "",
                "device_id": r.get("device_id") or "",
                "status": st or "FAIL",
                "failure_reason": r.get("failure_reason")
                or r.get("reason")
                or ("MAESTRO_FAILED" if st == "FAIL" else st),
                "ai_analysis": r.get("ai_analyses") or r.get("ai_analysis") or "—",
                "screenshot_artifact": r.get("screenshot_artifact") or "",
                "video_artifact": r.get("video_artifact") or "",
            }
        )
    return out


def merge_failed_rows(
    *,
    summary_rows: list[dict[str, Any]],
    excel_fail_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer artifact summary for video/screenshot; keep Excel AI text when present."""
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def _key(r: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(r.get("suite") or "").casefold(),
            str(r.get("test_name") or r.get("flow") or "").strip(),
            str(r.get("device_id") or r.get("device") or "").strip(),
        )

    for r in excel_fail_rows:
        by_key[_key(r)] = dict(r)

    for r in summary_rows:
        k = _key(r)
        base = by_key.get(k, {})
        merged = dict(base)
        merged.update({kk: vv for kk, vv in r.items() if vv not in ("", None)})
        # Preserve AI from Excel when summary has none
        ai = str(merged.get("ai_analysis") or merged.get("ai_analyses") or "").strip()
        if not ai or ai == "—":
            ai = str(base.get("ai_analysis") or base.get("ai_analyses") or "—").strip() or "—"
        merged["ai_analysis"] = ai
        if not merged.get("failure_reason"):
            merged["failure_reason"] = "MAESTRO_FAILED"
        if not merged.get("status"):
            merged["status"] = "FAIL"
        by_key[k] = merged

    rows = list(by_key.values())
    rows.sort(
        key=lambda r: (
            str(r.get("suite") or ""),
            str(r.get("test_name") or r.get("flow") or ""),
            str(r.get("device_id") or ""),
        )
    )
    return rows


def render_failed_tests_html(
    rows: list[dict[str, Any]],
    *,
    artifact_url: str | None = None,
    title: str = "Failed Tests",
    project_name: str = "Kodak Smile",
) -> str:
    """Render the Failed Tests table exactly like the Jenkins email section."""
    if not rows:
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:14px;color:#1a1a1a;margin:24px}}
.sub{{color:#1b5e20;font-weight:600}}
</style></head><body>
<h1>{html.escape(project_name)} — {html.escape(title)}</h1>
<p class="sub">No failed tests detected.</p>
</body></html>"""

    trs = [
        "<tr>"
        "<th>Suite</th><th>Flow</th><th>Device</th><th>Status</th>"
        "<th>Failure Reason</th><th>AI Analysis</th><th>Screenshot</th><th>Video</th>"
        "</tr>"
    ]
    for row in rows:
        suite = str(row.get("suite") or "—")
        name = str(row.get("test_name") or row.get("flow") or "—")
        device = str(row.get("device") or row.get("device_id") or "—")
        status = str(row.get("status") or "FAIL")
        reason = str(
            row.get("failure_reason") or row.get("reason") or row.get("error_message") or "—"
        )
        ai = str(row.get("ai_analysis") or row.get("ai_analyses") or "—").strip() or "—"
        shot = str(row.get("screenshot_artifact") or "").strip()
        video = str(row.get("video_artifact") or "").strip()

        shot_cell = html.escape(shot) if shot else "—"
        video_cell = html.escape(video) if video else "—"
        if artifact_url and shot:
            shot_url = jenkins_artifact_url(f"build-summary/failed-artifacts/{shot}")
            if shot_url:
                shot_cell = f'<a href="{html.escape(shot_url)}">{html.escape(shot)}</a>'
        if artifact_url and video:
            video_url = jenkins_artifact_url(f"build-summary/failed-artifacts/{video}")
            if video_url:
                video_cell = f'<a href="{html.escape(video_url)}">{html.escape(video)}</a>'
            elif not video_url and video:
                # Local relative link when not on Jenkins
                video_cell = (
                    f'<a href="../build-summary/failed-artifacts/{html.escape(video)}">'
                    f"{html.escape(video)}</a>"
                )

        ai_disp = ai if len(ai) <= 200 else ai[:200] + "…"
        trs.append(
            "<tr>"
            f"<td>{html.escape(suite)}</td>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(device)}</td>"
            f'<td class="st-fail"><strong>{html.escape(status)}</strong></td>'
            f"<td>{html.escape(reason)}</td>"
            f'<td class="c-ai" title="{html.escape(ai, quote=True)}">{html.escape(ai_disp)}</td>'
            f"<td>{shot_cell}</td>"
            f"<td>{video_cell}</td>"
            "</tr>"
        )

    footer = ""
    if artifact_url:
        footer = (
            '<p class="sub" style="margin-top:14px"><b>Failed Test Artifacts:</b> '
            f'<a href="{html.escape(artifact_url)}">{html.escape(artifact_url)}</a></p>'
        )
    else:
        local_zip = "build-summary/failed_tests_artifacts.zip"
        footer = (
            '<p class="sub" style="margin-top:14px"><b>Failed Test Artifacts:</b> '
            f'<code>{html.escape(local_zip)}</code> '
            "(set BUILD_URL on Jenkins for a clickable artifact link)</p>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(project_name)} — {html.escape(title)}</title>
<style>
  body {{ font-family: Calibri, "Segoe UI", Arial, sans-serif; font-size: 14px; color: #1a1a1a; margin: 24px; }}
  h1 {{ color: #1f4e79; font-size: 20px; margin-bottom: 8px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 16px; }}
  .heading {{ margin: 12px 0 6px; font-weight: 600; color: #1f4e79; }}
  table.ex {{ border-collapse: collapse; width: 100%; max-width: 1200px; border: 1px solid #000; }}
  table.ex th, table.ex td {{ border: 1px solid #000; padding: 8px 10px; text-align: left; vertical-align: top; word-break: break-word; }}
  table.ex th {{ background: #2e5c8a; color: #fff; font-weight: 600; }}
  .st-fail {{ color: #b71c1c; background: #ffebee; font-weight: bold; }}
  .c-ai {{ max-width: 280px; font-size: 13px; line-height: 1.35; color: #222; }}
  a {{ color: #1565c0; }}
</style>
</head>
<body>
  <h1>{html.escape(project_name)} Execution Summary</h1>
  <p class="heading">{html.escape(title)}</p>
  <table class="ex" role="presentation">{"".join(trs)}</table>
  {footer}
</body>
</html>"""


def write_failed_tests_report(
    repo: Path,
    out_path: Path,
    *,
    excel_fail_rows: list[dict[str, Any]] | None = None,
) -> Path:
    """Build and write failed_tests.html under the given path."""
    repo = repo.resolve()
    summary_rows = load_failed_summary(repo)
    excel_rows = excel_fail_rows or []
    rows = merge_failed_rows(summary_rows=summary_rows, excel_fail_rows=excel_rows)
    zip_path = repo / "build-summary" / "failed_tests_artifacts.zip"
    artifact_url = None
    if zip_path.is_file():
        artifact_url = jenkins_artifact_url("build-summary/failed_tests_artifacts.zip")
        if not artifact_url:
            # file:// fallback for local browsing
            artifact_url = zip_path.as_uri()
    html_doc = render_failed_tests_html(rows, artifact_url=artifact_url)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    # Also dump JSON companion for tooling
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps({"failures": rows, "count": len(rows)}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
