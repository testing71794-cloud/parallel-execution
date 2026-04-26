"""Runtime configuration (env + DEBUG)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE", os.getcwd())).resolve()


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


# Debug: save intermediates, verbose logs, skip email side effects in orchestrator
DEBUG_MODE: bool = _truthy("INTELLIGENT_PLATFORM_DEBUG", "0")

# Transport retries per model (each of primary / fallback)
AI_MAX_RETRIES: int = max(0, min(2, int(os.environ.get("AI_MAX_RETRIES", "2"))))

# OpenRouter — read OpenRouterAPI first (project default env name; never log the value)
# Key is re-read from os.environ on every access (Jenkins withCredentials, late env).
_OPENROUTER_KEY_CANDIDATES: tuple[str, ...] = (
    "OpenRouterAPI",
    "OPENROUTER_API_KEY",
    "OPENROUTER_KEY",
)


def openrouter_api_key() -> str:
    m = sys.modules[__name__]
    p = m.__dict__.get("OPENROUTER_API_KEY")
    if isinstance(p, str) and p.strip():
        return p.strip()
    for _k in _OPENROUTER_KEY_CANDIDATES:
        v = (os.environ.get(_k) or "").strip()
        v = v.strip('"').strip("'")
        if v:
            return v
    return ""


OPENROUTER_BASE_URL: str = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
# OpenRouter expects a site URL for free-tier routing; empty referer can yield empty model output.
OPENROUTER_HTTP_REFERER: str = (os.environ.get("OPENROUTER_HTTP_REFERER", "") or "http://localhost").strip()
OPENROUTER_APP_TITLE: str = (os.environ.get("OPENROUTER_APP_TITLE", "") or "Kodak Smile Automation").strip()

# OpenRouter model IDs (override with OPENROUTER_MODEL_*; fallback_2 default is "rules" = not an API call)
_DEFAULT_MODEL_PRIMARY: str = "mistralai/mistral-7b-instruct"
_DEFAULT_MODEL_FB1: str = "meta-llama/llama-3.3-70b-instruct:free"
_DEFAULT_MODEL_FB2: str = "rules"


def openrouter_model_primary() -> str:
    s = (os.environ.get("OPENROUTER_MODEL_PRIMARY", "") or _DEFAULT_MODEL_PRIMARY).strip()
    return s or _DEFAULT_MODEL_PRIMARY


def openrouter_model_fallback_1() -> str:
    s = (os.environ.get("OPENROUTER_MODEL_FALLBACK_1", "") or _DEFAULT_MODEL_FB1).strip()
    return s or _DEFAULT_MODEL_FB1


def openrouter_model_fallback_2() -> str:
    s = (os.environ.get("OPENROUTER_MODEL_FALLBACK_2", "") or _DEFAULT_MODEL_FB2).strip()
    return s or _DEFAULT_MODEL_FB2


def openrouter_key_env_name_used() -> str:
    return next((k for k in _OPENROUTER_KEY_CANDIDATES if (os.environ.get(k) or "").strip()), "")


def openrouter_key_present() -> bool:
    return bool(openrouter_api_key())

# Optional: direct OpenAI (other tooling); intelligent_platform uses OpenRouter when key is set
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openrouter_configured() -> bool:
    return openrouter_key_present()


def ai_health_marks_unavailable() -> bool:
    """If build-summary/ai_status.txt says UNAVAILABLE, skip OpenRouter in analyzers."""
    p = workspace_root() / "build-summary" / "ai_status.txt"
    if not p.is_file():
        return False
    try:
        return "AI_STATUS=UNAVAILABLE" in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

# Email: orchestrator does not send mail; set to skip writing failed_summary for email pickup
SKIP_EMAIL_ARTIFACTS: bool = _truthy("INTELLIGENT_PLATFORM_SKIP_EMAIL", "0")
