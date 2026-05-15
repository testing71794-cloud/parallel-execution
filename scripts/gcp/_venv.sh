#!/usr/bin/env bash
# Shared venv for GCP orchestrator (PEP 668 / externally-managed-environment safe).
# Persistent on the agent so later stages survive workspace deleteDir + unstash.
#
# Preferred: python3-venv (e.g. sudo apt install -y python3.12-venv)
# Fallback: pip --user with PIP_BREAK_SYSTEM_PACKAGES when venv cannot be created.

_gcp_python_minor_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

_gcp_pip_user_install() {
  local PY_BOOT="$1"
  local ROOT="$2"
  export GCP_PYTHON_MODE="${GCP_PYTHON_MODE:-user}"
  export PY="$PY_BOOT"
  export PATH="${HOME}/.local/bin:${PATH}"
  export PIP_BREAK_SYSTEM_PACKAGES=1
  echo "[gcp-venv] Using PY=$PY (user site-packages; not isolated venv)"
  if ! "$PY" -m pip install --user --upgrade pip --quiet 2>/dev/null; then
    "$PY" -m pip install --user --upgrade pip --break-system-packages --quiet
  fi
  if ! "$PY" -m pip install --user -r "$ROOT/scripts/requirements-python.txt" --quiet 2>/dev/null; then
    "$PY" -m pip install --user -r "$ROOT/scripts/requirements-python.txt" --break-system-packages --quiet
  fi
}

_gcp_venv_has_pip() {
  local PY_VENV="$1"
  "$PY_VENV" -m pip --version >/dev/null 2>&1
}

_gcp_repair_venv_pip() {
  local PY_VENV="$1"
  echo "[gcp-venv] bootstrapping pip in existing venv ($PY_VENV)"
  if "$PY_VENV" -m ensurepip --upgrade >/dev/null 2>&1 && _gcp_venv_has_pip "$PY_VENV"; then
    return 0
  fi
  if "$PY_VENV" -m ensurepip >/dev/null 2>&1 && _gcp_venv_has_pip "$PY_VENV"; then
    return 0
  fi
  return 1
}

_gcp_venv_pip_install() {
  local PY_VENV="$1"
  local ROOT="$2"
  if ! _gcp_venv_has_pip "$PY_VENV"; then
    echo "[gcp-venv] ERROR: venv python has no pip: $PY_VENV" >&2
    return 1
  fi
  export GCP_PYTHON_MODE="${GCP_PYTHON_MODE:-venv}"
  export PY="$PY_VENV"
  export PIP="${PY_VENV%/python}/pip"
  echo "[gcp-venv] Using PY=$PY (venv)"
  "$PY" -m pip install --upgrade pip --quiet
  "$PY" -m pip install -r "$ROOT/scripts/requirements-python.txt" --quiet
}

resolve_gcp_python() {
  local ROOT="${1:-.}"
  local VENV_DIR="${JENKINS_ORCHESTRATOR_VENV:-${HOME}/jenkins-venvs/kodak-atp-orchestrator}"
  mkdir -p "$(dirname "$VENV_DIR")"

  local PY_BOOT="${PYTHON_BOOT:-}"
  if [[ -z "$PY_BOOT" ]]; then
    for c in python3.13 python3.12 python3.11 python3; do
      if command -v "$c" >/dev/null 2>&1; then PY_BOOT="$(command -v "$c")"; break; fi
    done
  fi
  if [[ -z "$PY_BOOT" ]]; then
    echo "[gcp-venv] ERROR: python3 not found"
    return 1
  fi

  # Reuse existing venv only when pip is usable (broken venvs lack ensurepip without python*-venv)
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    local PY_VENV="$VENV_DIR/bin/python"
    if _gcp_venv_has_pip "$PY_VENV"; then
      _gcp_venv_pip_install "$PY_VENV" "$ROOT"
      return 0
    fi
    echo "[gcp-venv] WARN: venv at $VENV_DIR exists but pip is missing"
    if _gcp_repair_venv_pip "$PY_VENV"; then
      _gcp_venv_pip_install "$PY_VENV" "$ROOT"
      return 0
    fi
    echo "[gcp-venv] removing broken venv (no pip) at $VENV_DIR"
    rm -rf "$VENV_DIR"
  elif [[ -d "$VENV_DIR" ]]; then
    echo "[gcp-venv] removing incomplete venv at $VENV_DIR"
    rm -rf "$VENV_DIR"
  fi

  local PY_MINOR
  PY_MINOR="$(_gcp_python_minor_version "$PY_BOOT")"
  local VENV_LOG
  VENV_LOG="$(mktemp)"
  trap 'rm -f "$VENV_LOG"' RETURN

  echo "[gcp-venv] creating venv at $VENV_DIR (boot=$PY_BOOT)"
  if "$PY_BOOT" -m venv "$VENV_DIR" >"$VENV_LOG" 2>&1 && [[ -x "$VENV_DIR/bin/python" ]]; then
    local PY_NEW="$VENV_DIR/bin/python"
    if ! _gcp_venv_has_pip "$PY_NEW"; then
      _gcp_repair_venv_pip "$PY_NEW" || true
    fi
    if _gcp_venv_has_pip "$PY_NEW"; then
      _gcp_venv_pip_install "$PY_NEW" "$ROOT"
      return 0
    fi
    echo "[gcp-venv] WARN: new venv still has no pip; removing $VENV_DIR"
    rm -rf "$VENV_DIR"
  fi

  # virtualenv module (if installed)
  if "$PY_BOOT" -m virtualenv "$VENV_DIR" >"$VENV_LOG" 2>&1 && [[ -x "$VENV_DIR/bin/python" ]]; then
    echo "[gcp-venv] created venv via python -m virtualenv"
    local PY_VE="$VENV_DIR/bin/python"
    if _gcp_venv_has_pip "$PY_VE" || _gcp_repair_venv_pip "$PY_VE"; then
      _gcp_venv_pip_install "$PY_VE" "$ROOT"
      return 0
    fi
    rm -rf "$VENV_DIR"
  fi

  cat "$VENV_LOG" >&2 || true
  echo "[gcp-venv] ERROR: could not create venv." >&2
  echo "[gcp-venv] On Ubuntu/Debian install (as root on the agent):" >&2
  echo "  sudo apt install -y python${PY_MINOR}-venv python3-pip" >&2
  echo "  # or: sudo apt install -y python3-venv" >&2

  if [[ "${JENKINS_ORCHESTRATOR_ALLOW_USER_PIP:-1}" == "0" ]]; then
    return 1
  fi

  echo "[gcp-venv] WARN: falling back to pip --user (install python${PY_MINOR}-venv when possible)" >&2
  _gcp_pip_user_install "$PY_BOOT" "$ROOT"
  return 0
}
