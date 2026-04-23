"""Runtime configuration (env + DEBUG)."""

from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE", os.getcwd())).resolve()


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


# Debug: save intermediates, verbose logs, skip email side effects in orchestrator
DEBUG_MODE: bool = _truthy("INTELLIGENT_PLATFORM_DEBUG", "0")

# Transport retries per model (each of primary / fallback)
AI_MAX_RETRIES: int = max(0, min(2, int(os.environ.get("AI_MAX_RETRIES", "2"))))

# OpenRouter (explicit models in openrouter_client — no auto-routing)
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_KEY", "")).strip()
OPENROUTER_BASE_URL: str = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_HTTP_REFERER: str = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
OPENROUTER_APP_TITLE: str = os.environ.get("OPENROUTER_APP_TITLE", "Kodak Intelligent Platform").strip()

# Optional: direct OpenAI (other tooling); intelligent_platform uses OpenRouter when key is set
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openrouter_configured() -> bool:
    return bool(OPENROUTER_API_KEY)

# Email: orchestrator does not send mail; set to skip writing failed_summary for email pickup
SKIP_EMAIL_ARTIFACTS: bool = _truthy("INTELLIGENT_PLATFORM_SKIP_EMAIL", "0")
