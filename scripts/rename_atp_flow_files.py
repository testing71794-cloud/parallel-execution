"""Rename main ATP flow files from SE_01 - Settings button.yaml to SE_01 - Settings button.yaml."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ATP_ROOT = REPO / "ATP TestCase Flows"
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
TC_FILE_PATTERN = re.compile(r"^[A-Z]{2,3}_[A-Z0-9]")
TEXT_SUFFIXES = {".yaml", ".yml", ".csv", ".json", ".md", ".txt", ".bat", ".ps1", ".sh", ".py"}


def collect_test_files() -> list[Path]:
    files: list[Path] = []
    for module in MODULES:
        module_dir = ATP_ROOT / module
        if not module_dir.is_dir():
            continue
        files.extend(
            p
            for p in sorted(module_dir.glob("*.yaml"))
            if TC_FILE_PATTERN.match(p.stem)
        )
    permission_test = ATP_ROOT / "SU_01 - I'll do it later.yaml"
    if permission_test.exists():
        files.append(permission_test)
    return files


def read_tc_id(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# TC_ID:"):
            return line.split(":", 1)[1].strip()
    return None


def filename_from_tc_id(tc_id: str) -> str:
    name = tc_id
    name = name.replace(" > ", " - ")
    name = name.replace(" / ", " - ")
    name = name.replace("/", "-")
    for char in '<>:"\\|?*':
        name = name.replace(char, "")
    return f"{name}.yaml"


def build_rename_map() -> dict[Path, Path]:
    rename_map: dict[Path, Path] = {}
    for path in collect_test_files():
        tc_id = read_tc_id(path)
        if not tc_id:
            print(f"SKIP (no # TC_ID): {path.relative_to(REPO)}")
            continue
        new_name = filename_from_tc_id(tc_id)
        new_path = path.with_name(new_name)
        if path.name == new_name:
            continue
        rename_map[path] = new_path
    return rename_map


def replace_in_file(path: Path, replacements: list[tuple[str, str]]) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        files.append(path)
    return files


def main() -> None:
    rename_map = build_rename_map()
    if not rename_map:
        print("No files to rename.")
        return

    replacements = sorted(
        ((old.name, new.name) for old, new in rename_map.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    rel_replacements = sorted(
        (
            (str(old.relative_to(REPO)).replace("\\", "/"), str(new.relative_to(REPO)).replace("\\", "/"))
            for old, new in rename_map.items()
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    print(f"Renaming {len(rename_map)} flow file(s):")
    for old, new in sorted(rename_map.items(), key=lambda item: str(item[0])):
        print(f"  {old.relative_to(REPO)} -> {new.name}")

    updated_refs = 0
    for path in iter_text_files():
        if replace_in_file(path, replacements) or replace_in_file(path, rel_replacements):
            updated_refs += 1

    for old, new in rename_map.items():
        if new.exists() and new != old:
            raise SystemExit(f"Target already exists: {new}")
        old.rename(new)

    print(f"Updated references in {updated_refs} file(s).")
    print("Done.")


if __name__ == "__main__":
    main()
