#!/usr/bin/env python3
"""Ensure OpenRouter verify server listens on 127.0.0.1:8765 (background, Jenkins/GA_02)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HOST = "127.0.0.1"
_PORT = 8765
_WAIT_SEC = int(os.environ.get("ATP_VERIFY_SERVER_WAIT_SEC", "20"))


def port_open(host: str = _HOST, port: int = _PORT, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def apply_maestro_graaljs_env() -> None:
    os.environ.setdefault("MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS", "1")
    os.environ.setdefault("MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_CLASS_LOOKUP", "1")


def ensure_verify_server(repo: Path | None = None, *, wait_sec: int | None = None) -> bool:
    repo = (repo or _REPO).resolve()
    wait = _WAIT_SEC if wait_sec is None else wait_sec
    if port_open():
        print(f"[verify_server] already listening on http://{_HOST}:{_PORT}", flush=True)
        return True
    script = repo / "scripts" / "maestro_openrouter_verify_server.py"
    if not script.is_file():
        print(f"[verify_server] ERROR: missing {script}", flush=True)
        return False
    print(f"[verify_server] starting background server on http://{_HOST}:{_PORT}", flush=True)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    log_dir = repo / "reports" / "gallery"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "verify_server.log"
    log_handle = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    subprocess.Popen(  # noqa: S603
        [sys.executable, str(script)],
        cwd=str(repo),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    for i in range(max(1, wait)):
        time.sleep(1)
        if port_open():
            print(f"[verify_server] ready after {i + 1}s (log={log_path})", flush=True)
            return True
    print(f"[verify_server] WARN: port {_PORT} not open after {wait}s (log={log_path})", flush=True)
    return False


def main() -> int:
    apply_maestro_graaljs_env()
    return 0 if ensure_verify_server() else 1


if __name__ == "__main__":
    raise SystemExit(main())
