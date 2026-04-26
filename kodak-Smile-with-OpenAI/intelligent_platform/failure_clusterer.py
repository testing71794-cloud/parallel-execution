"""
Group similar failures using normalized error text + screen + step.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger("intelligent_platform.cluster")


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"0x[0-9a-f]+", "0x", s)
    s = re.sub(r"\b\d+\b", "#", s)
    s = re.sub(r"\s+", " ", s)
    return s[:800]


def _group_key(f: dict[str, Any]) -> str:
    key_src = "|".join(
        [
            _norm(str(f.get("error_message", ""))),
            _norm(str(f.get("screen", ""))),
            _norm(str(f.get("step_failed", ""))),
        ]
    )
    return hashlib.sha256(key_src.encode("utf-8", errors="ignore")).hexdigest()[:12]


def cluster_failures(
    failures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Returns (cluster rows for JSON/report, cluster_id for each input failure in order).
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in failures:
        groups[_group_key(f)].append(f)

    cluster_rows: list[dict[str, Any]] = []
    hid_to_label: dict[str, str] = {}
    for idx, (hid, members) in enumerate(
        sorted(groups.items(), key=lambda x: -len(x[1])), start=1
    ):
        label = f"CLUSTER_{idx}"
        hid_to_label[hid] = label
        root_issue = (members[0].get("root_cause") or members[0].get("error_message", ""))[
            :200
        ]
        if not root_issue.strip():
            root_issue = members[0].get("test_name", "unknown") or "grouped failure"
        affected = sorted({str(m.get("test_name", "unknown")) for m in members})
        cluster_rows.append(
            {
                "cluster_id": label,
                "root_issue": root_issue,
                "affected_tests": affected,
                "count": len(members),
            }
        )
    per_row = [hid_to_label[_group_key(f)] for f in failures]
    logger.info("Formed %s cluster(s)", len(cluster_rows))
    return cluster_rows, per_row
