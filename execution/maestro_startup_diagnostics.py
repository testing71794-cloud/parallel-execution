#!/usr/bin/env python3
"""Startup telemetry for Maestro readiness debugging (Jenkins / Windows)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping


def _safe_slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value.strip()) or "unknown"


class StartupDiagnostics:
    """Writes startup_trace.log, env snapshot, and log tails under reports/<suite>/startup-diagnostics/."""

    def __init__(
        self,
        *,
        repo: Path,
        suite_id: str,
        device_id: str,
        flow_name: str,
    ) -> None:
        slug = _safe_slug(device_id)
        self.dir = (
            repo / "reports" / suite_id / "startup-diagnostics" / f"{_safe_slug(flow_name)}__{slug}"
        ).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.dir / "startup_trace.log"
        self.stdout_path = self.dir / "maestro_stdout.log"
        self.stderr_path = self.dir / "maestro_stderr.log"
        self.process_tree_path = self.dir / "process_tree.log"

    def trace(self, message: str, **fields: Any) -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        extra = " ".join(f"{k}={fields[k]!r}" for k in sorted(fields)) if fields else ""
        line = f"{ts} {message} {extra}".rstrip() + "\n"
        print(f"[ATP] startup_trace {message}" + (f" {extra}" if extra else ""), flush=True)
        try:
            with self.trace_path.open("a", encoding="utf-8", errors="replace") as f:
                f.write(line)
                f.flush()
        except OSError:
            pass

    def log_environment(self, env: Mapping[str, str], *, label: str = "orchestrator_child") -> None:
        keys = (
            "JAVA_HOME",
            "MAESTRO_HOME",
            "MAESTRO_JAVA_HOME",
            "ATP_JAVA_USER_HOME",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "ANDROID_SERIAL",
            "ATP_MAESTRO_DRIVER_PORT",
            "ATP_MAESTRO_JAVA_DIRECT",
            "ATP_MAESTRO_RUNTIME_ROOT",
            "MAESTRO_OPTS",
        )
        lines = [f"label={label}", f"ts={time.time():.3f}"]
        for key in keys:
            val = env.get(key, "")
            if val:
                lines.append(f"{key}={val}")
        path = self.dir / "env_snapshot.txt"
        try:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
        self.trace("env_snapshot_written", path=str(path))

    def log_command(self, argv: list[str], *, cwd: str | Path) -> None:
        self.trace("subprocess_argv", argv=argv, cwd=str(cwd))
        try:
            (self.dir / "subprocess_argv.json").write_text(
                json.dumps({"argv": argv, "cwd": str(cwd)}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def snapshot_flow_log(
        self,
        log_path: Path,
        *,
        start_offset: int = 0,
        label: str = "poll",
    ) -> int:
        """Copy new bytes from per-flow log into maestro_stdout.log; return current file size."""
        if not log_path.is_file():
            return 0
        try:
            size = log_path.stat().st_size
            if size <= start_offset:
                return size
            with log_path.open("rb") as src:
                src.seek(start_offset)
                chunk = src.read(min(size - start_offset, 256_000))
            if chunk:
                with self.stdout_path.open("ab") as out:
                    out.write(f"\n--- {label} offset={start_offset} ---\n".encode("utf-8", errors="replace"))
                    out.write(chunk)
                    out.flush()
            return size
        except OSError:
            return start_offset

    def write_process_tree(self, text: str) -> None:
        try:
            self.process_tree_path.write_text(text, encoding="utf-8", errors="replace")
        except OSError:
            pass
