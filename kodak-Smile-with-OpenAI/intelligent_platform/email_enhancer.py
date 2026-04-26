"""Build intelligent email body text for Jenkins send_execution_email (failed_summary.txt)."""

from __future__ import annotations

from typing import Any


def build_email_summary(
    analyzed: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    total: int,
    passed: int,
    failed: int,
) -> str:
    lines = [
        "=== Intelligent test automation summary ===",
        f"Total: {total}  |  Passed: {passed}  |  Failed: {failed}",
        "",
        "--- Top failure clusters ---",
    ]
    for c in clusters[:5]:
        lines.append(
            f"• {c.get('cluster_id')} (x{c.get('count', 0)}): {c.get('root_issue', '')[:120]}"
        )
        for t in (c.get("affected_tests") or [])[:6]:
            lines.append(f"    - {t}")
    lines += ["", "--- AI insights (per failure) ---"]
    for a in analyzed[:20]:
        lines.append(
            f"• {a.get('test_name', '?')[:80]} [{a.get('category', '')}] conf={a.get('confidence', 0):.2f}"
        )
        lines.append(f"  Root: {str(a.get('root_cause', ''))[:200]}")
        lines.append(f"  Fix:  {str(a.get('suggestion', ''))[:200]}")
    if len(analyzed) > 20:
        lines.append(f"... and {len(analyzed) - 20} more (see ai_intelligence_report.xlsx).")

    lines += [
        "",
        "Recommended actions:",
        "1) Tackle highest-count clusters first (see Clusters sheet).",
        "2) If category is 'locator' or 'timing', update Maestro flow stability.",
        "3) If 'crash' or 'api' with is_test_issue=no, file an app bug with log excerpt.",
    ]
    return "\n".join(lines)
