#!/usr/bin/env python3
"""Patch generate_permission_flows.py CASES to Camera-first PM numbering."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "scripts" / "generate_permission_flows.py"

OLD_FROM_NEW: dict[str, str] = {
    "PM_01": "PM_05",
    "PM_02": "PM_06",
    "PM_03": "PM_07",
    "PM_04": "PM_08",
    "PM_05": "PM_16",
    "PM_06": "PM_17",
    "PM_07": "PM_18",
    "PM_08": "PM_19",
    "PM_09": "PM_13",
    "PM_10": "PM_14",
    "PM_11": "PM_15",
    "PM_12": "PM_01",
    "PM_13": "PM_02",
    "PM_14": "PM_03",
    "PM_15": "PM_04",
    "PM_16": "PM_09",
    "PM_17": "PM_10",
    "PM_18": "PM_11",
    "PM_19": "PM_12",
}

TITLE_OVERRIDES: dict[str, str] = {
    "PM_09": "Nearby Devices Permission Allow",
    "PM_10": "Nearby Devices Permission Deny",
    "PM_11": "Nearby Devices Permission Enable Later",
    "PM_16": "Photos and Videos Permission Allow All",
    "PM_17": "Photos and Videos Permission Limited Access",
    "PM_18": "Photos and Videos Permission Deny",
    "PM_19": "Photos and Videos Permission Don't Ask Again",
}

NEW_ORDER = [f"PM_{i:02d}" for i in range(1, 28)]


def main() -> int:
    text = GEN.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\(\s*"(PM_\d+)",\s*"(.*?)",\s*"(.*?)",\s*"(.*?)",\s*f"""(.*?)""",\s*(\d+),\s*\)',
        re.DOTALL,
    )
    cases_by_id = {m.group(1): m.groups() for m in pattern.finditer(text)}
    if len(cases_by_id) != 27:
        raise RuntimeError(f"Expected 27 cases, found {len(cases_by_id)}")

    blocks: list[str] = []
    for new_id in NEW_ORDER:
        old_id = OLD_FROM_NEW.get(new_id, new_id)
        tc_id, title, steps, expected, body, step_count = cases_by_id[old_id]
        title = TITLE_OVERRIDES.get(new_id, title)
        blocks.append(
            f'    (\n'
            f'        "{new_id}",\n'
            f'        "{title}",\n'
            f'        "{steps}",\n'
            f'        "{expected}",\n'
            f'        f"""{body}""",\n'
            f'        {step_count},\n'
            f'    )'
        )

    new_cases = "CASES: list[tuple[str, str, str, str, str, int]] = [\n" + ",\n".join(blocks) + ",\n]"
    text = re.sub(
        r"CASES: list\[tuple\[str, str, str, str, str, int\]\] = \[.*?\]\n\n\ndef write_flows",
        new_cases + "\n\n\ndef write_flows",
        text,
        count=1,
        flags=re.DOTALL,
    )
    text = text.replace(
        '"""Generate PM_01–PM_27 permission ATP flows aligned with video order and project subflows."""',
        '"""Generate PM_01–PM_27 permission ATP flows (Camera-first order) and project subflows."""',
    )
    GEN.write_text(text, encoding="utf-8", newline="\n")
    print(f"Patched {GEN.name} CASES order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
