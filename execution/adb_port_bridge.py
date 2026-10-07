"""
TCP bridge: localhost:5037 -> ADB_SERVER_PORT (default 5038).

Maestro/dadb hardcodes discovery to localhost:5037 and does not honor
ADB_SERVER_PORT / ANDROID_ADB_SERVER_PORT (see mobile-dev-inc/maestro#3461).
This agent keeps the real adb daemon on 5038 (5037 hangs), so without a bridge
Maestro reports: "Device X was requested, but it is not connected."
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

MAESTRO_ADB_PORT = 5037
_BRIDGE_PID_NAME = "adb_port_bridge.pid"
_BRIDGE_MARK = "atp_adb_port_bridge"


def _repo_lock_dir(repo: Path | None = None) -> Path:
    root = repo
    if root is None:
        env_root = (os.environ.get("ATP_REPO_ROOT") or os.environ.get("WORKSPACE") or "").strip()
        root = Path(env_root) if env_root else Path.cwd()
    d = (root / ".maestro-runtime" / "_adb_bridge").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_file(repo: Path | None = None) -> Path:
    return _repo_lock_dir(repo) / _BRIDGE_PID_NAME


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return str(pid) in (out.stdout or "")
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_bridge_pid(repo: Path | None = None) -> int | None:
    pf = _pid_file(repo)
    try:
        raw = pf.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw.isdigit():
        return None
    pid = int(raw)
    return pid if _pid_alive(pid) else None


def _write_bridge_pid(pid: int, repo: Path | None = None) -> None:
    try:
        _pid_file(repo).write_text(str(pid), encoding="utf-8")
    except OSError:
        pass


def _clear_bridge_pid(repo: Path | None = None) -> None:
    try:
        _pid_file(repo).unlink(missing_ok=True)
    except OSError:
        pass


def _kill_listener_on_port(port: int) -> None:
    """Best-effort free MAESTRO_ADB_PORT so the bridge can bind (Windows)."""
    if os.name != "nt":
        return
    try:
        # adb kill-server on 5037 (may hang — hard timeout)
        adb = (os.environ.get("ADB_EXE") or "").strip() or "adb"
        subprocess.run(
            [adb, "-P", str(port), "kill-server"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        ps = (
            f"$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue; "
            f"if ($c) {{ $c.OwningProcess | Sort-Object -Unique | ForEach-Object {{ "
            f"Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }} }}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _relay(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        try:
            a.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            b.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            a.close()
        except OSError:
            pass
        try:
            b.close()
        except OSError:
            pass


def _serve(listen_port: int, target_port: int) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(64)
    while True:
        client, _addr = srv.accept()
        try:
            upstream = socket.create_connection(("127.0.0.1", target_port), timeout=10)
        except OSError:
            try:
                client.close()
            except OSError:
                pass
            continue
        threading.Thread(target=_relay, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_relay, args=(upstream, client), daemon=True).start()


def run_bridge_foreground(target_port: int, listen_port: int = MAESTRO_ADB_PORT) -> int:
    """Blocking server process (spawned as detached child)."""
    print(
        f"[{_BRIDGE_MARK}] listen=127.0.0.1:{listen_port} -> 127.0.0.1:{target_port} pid={os.getpid()}",
        flush=True,
    )
    _serve(listen_port, target_port)
    return 0


def ensure_maestro_adb_bridge(
    *,
    repo: Path | None = None,
    target_port: str | int | None = None,
    listen_port: int = MAESTRO_ADB_PORT,
) -> dict[str, object]:
    """
    Ensure Maestro can discover devices when the real adb daemon is not on 5037.
    Returns a small status dict for logging.
    """
    from .subprocess_launch import ensure_adb_server_port_env

    real_port = int(str(target_port or ensure_adb_server_port_env()).strip() or "5038")
    status: dict[str, object] = {
        "needed": real_port != listen_port,
        "listen_port": listen_port,
        "target_port": real_port,
        "started": False,
        "reused": False,
        "ok": False,
        "detail": "",
    }
    # Future Maestro builds that honor ANDROID_ADB_SERVER_PORT
    os.environ["ANDROID_ADB_SERVER_PORT"] = str(real_port)
    os.environ["ADB_SERVER_PORT"] = str(real_port)

    if real_port == listen_port:
        status["ok"] = True
        status["detail"] = "adb already on Maestro default port"
        return status

    existing = _read_bridge_pid(repo)
    if existing and _port_open("127.0.0.1", listen_port):
        status["ok"] = True
        status["reused"] = True
        status["detail"] = f"bridge_pid={existing}"
        return status

    if _port_open("127.0.0.1", listen_port):
        # Something else holds 5037 (often hung adb). Free it for the bridge.
        status["detail"] = f"freeing stale listener on {listen_port}"
        _kill_listener_on_port(listen_port)
        time.sleep(0.5)

    if not _port_open("127.0.0.1", real_port):
        status["detail"] = f"target adb port {real_port} not listening"
        return status

    # Spawn detached bridge process (python -m so package import works on Jenkins).
    root = Path(
        repo
        or (os.environ.get("ATP_REPO_ROOT") or os.environ.get("WORKSPACE") or Path.cwd())
    ).resolve()
    cmd = [
        sys.executable,
        "-m",
        "execution.adb_port_bridge",
        "serve",
        str(real_port),
        str(listen_port),
    ]
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(root) + os.pathsep + child_env.get("PYTHONPATH", "")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=(os.name != "nt"),
        )
    except OSError as e:
        status["detail"] = f"spawn_failed:{e}"
        return status

    _write_bridge_pid(proc.pid, repo)
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if _port_open("127.0.0.1", listen_port):
            status["ok"] = True
            status["started"] = True
            status["detail"] = f"bridge_pid={proc.pid}"
            return status
        time.sleep(0.2)

    status["detail"] = f"bridge_started_but_port_not_open pid={proc.pid}"
    return status


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "serve":
        target = int(args[1]) if len(args) > 1 else int(os.environ.get("ADB_SERVER_PORT") or "5038")
        listen = int(args[2]) if len(args) > 2 else MAESTRO_ADB_PORT
        return run_bridge_foreground(target, listen)
    st = ensure_maestro_adb_bridge()
    print(f"[{_BRIDGE_MARK}] {st}", flush=True)
    return 0 if st.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
