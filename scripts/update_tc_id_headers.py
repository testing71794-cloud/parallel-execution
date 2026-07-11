"""Normalize # TC_ID and name: fields to 'XX_XX - Title' across main ATP flows."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ATP TestCase Flows"
TC_FILE_PATTERN = re.compile(r"^[A-Z]{2,3}_[A-Z0-9]")
MODULES = [
    "camera",
    "collage",
    "connection",
    "editing",
    "gallery",
    "onboarding",
    "precut",
    "printing",
    "settings",
    "signup-login",
]


def normalize_title(tc_id: str, title: str) -> str:
    title = title.replace("_", " ")
    replacements = {
        "Ill Do It Later": "I'll do it later",
        "Log In": "Log in",
        "Auto Connect": "Auto-connect",
    }
    for old, new in replacements.items():
        title = title.replace(old, new)
    return f"{tc_id} - {title}"


def parse_name(raw: str) -> str:
    raw = raw.strip().strip('"')
    if " - " in raw:
        return raw
    match = re.match(r"^([A-Z]{2}_[A-Z0-9]+(?:[A-Z])?)_(.+)$", raw)
    if match:
        return normalize_title(match.group(1), match.group(2))
    return raw


def process_file(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    canonical = None
    name_quoted = False
    for line in lines:
        if line.startswith("name:"):
            rest = line.split("name:", 1)[1].strip()
            name_quoted = rest.startswith('"')
            raw = rest.strip('"').strip()
            canonical = parse_name(raw)
            break
    if not canonical:
        return None

    new_lines = []
    for line in lines:
        if re.match(r"^# TC_ID:", line):
            continue
        if re.match(r"^# ATP Name:", line):
            continue
        new_lines.append(line)

    for index, line in enumerate(new_lines):
        if line.startswith("name:"):
            if name_quoted:
                new_lines[index] = f'name: "{canonical}"\n'
            else:
                new_lines[index] = f"name: {canonical}\n"
            break

    tc_line = f"# TC_ID: {canonical}\n"
    if new_lines and new_lines[0].startswith("# TC_ID:"):
        new_lines[0] = tc_line
    else:
        new_lines.insert(0, tc_line)

    new_content = "".join(new_lines)
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return canonical
    return None


def main() -> None:
    files = collect_test_files()
    updated: list[tuple[str, str]] = []
    for path in files:
        result = process_file(path)
        if result:
            updated.append((str(path.relative_to(ROOT.parent)), result))

    print(f"Processed {len(files)} files, updated {len(updated)}")
    for file_path, tc_id in updated:
        print(f"  {file_path}: {tc_id}")


def collect_test_files() -> list[Path]:
    files: list[Path] = []
    for module in MODULES:
        module_dir = ROOT / module
        if not module_dir.is_dir():
            continue
        files.extend(
            p
            for p in sorted(module_dir.glob("*.yaml"))
            if TC_FILE_PATTERN.match(p.stem)
        )
    permission_test = ROOT / "SU_01 - I'll do it later.yaml"
    if permission_test.exists():
        files.append(permission_test)
    return files


def verify() -> int:
    files = collect_test_files()
    mismatches = []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        tc = next((line for line in lines if line.startswith("# TC_ID:")), None)
        nm = next((line for line in lines if line.startswith("name:")), None)
        if not tc or not nm:
            mismatches.append((path.name, "missing header"))
            continue
        tc_value = tc.split(":", 1)[1].strip()
        name_value = nm.split(":", 1)[1].strip().strip('"')
        if tc_value != name_value:
            mismatches.append((path.name, tc_value, name_value))

    if mismatches:
        print(f"Mismatches: {len(mismatches)}")
        for item in mismatches:
            print(" ", item)
        return 1
    print(f"All {len(files)} main flows have matching # TC_ID and name:")
    return 0


if __name__ == "__main__":
    main()
    raise SystemExit(verify())
